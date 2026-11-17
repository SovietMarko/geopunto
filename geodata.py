# -*- coding: utf-8 -*-
"""Logica sin interfaz de Geopunto: proyectos, marca de agua y exportacion a Excel.

Este modulo no depende de Kivy para poder probarlo en cualquier PC.
"""
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageOps

FIXED_COLUMNS = ["Latitud", "Longitud", "Fecha"]
MAX_PHOTOS = 5
DATE_FMT = "%Y-%m-%d %H:%M:%S"
CRS_LABEL = "EPSG:4326 - WGS 84"


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or "proyecto"


def standard_column_names(n):
    return ["dato_%d" % (i + 1) for i in range(n)]


def build_column_names(n, custom=None):
    """Devuelve n nombres de columna validos.

    custom: lista opcional con nombres escritos por el usuario. Los vacios se
    reemplazan por dato_i. Lanza ValueError si hay duplicados o si se usa un
    nombre reservado (Latitud, Longitud, Fecha).
    """
    if n < 1:
        raise ValueError("La cantidad de columnas debe ser al menos 1.")
    names = standard_column_names(n)
    if custom:
        for i in range(n):
            if i < len(custom) and custom[i] and custom[i].strip():
                names[i] = custom[i].strip()
    reserved = {c.lower() for c in FIXED_COLUMNS}
    seen = set()
    for name in names:
        key = name.lower()
        if key in reserved:
            raise ValueError('"%s" es un nombre reservado.' % name)
        if key in seen:
            raise ValueError('La columna "%s" esta repetida.' % name)
        seen.add(key)
    return names


def format_coord(value):
    return "%.7f" % value


# --------------------------------------------------------------------------
# Proyectos
# --------------------------------------------------------------------------
class Project(object):
    FILE = "proyecto.json"

    def __init__(self, folder, data):
        self.folder = folder
        self.data = data

    # ---- propiedades ----
    @property
    def name(self):
        return self.data["nombre"]

    @property
    def columns(self):
        return self.data["columnas"]

    @property
    def points(self):
        return self.data["puntos"]

    @property
    def photos_dir(self):
        path = os.path.join(self.folder, "fotos")
        if not os.path.isdir(path):
            os.makedirs(path)
        return path

    # ---- creacion / carga ----
    @classmethod
    def create(cls, base_dir, name, columns):
        name = name.strip()
        if not name:
            raise ValueError("Escribe el nombre del proyecto.")
        folder = os.path.join(base_dir, slugify(name))
        if os.path.exists(os.path.join(folder, cls.FILE)):
            raise ValueError('Ya existe un proyecto llamado "%s".' % name)
        os.makedirs(folder, exist_ok=True)
        data = {
            "nombre": name,
            "columnas": list(columns),
            "creado": datetime.now().strftime(DATE_FMT),
            "siguiente_id": 1,
            "puntos": [],
        }
        project = cls(folder, data)
        project.save()
        return project

    @classmethod
    def load(cls, folder):
        with open(os.path.join(folder, cls.FILE), "r", encoding="utf-8") as fh:
            return cls(folder, json.load(fh))

    @classmethod
    def list_all(cls, base_dir):
        projects = []
        if not os.path.isdir(base_dir):
            return projects
        for entry in sorted(os.listdir(base_dir)):
            folder = os.path.join(base_dir, entry)
            if os.path.isfile(os.path.join(folder, cls.FILE)):
                try:
                    projects.append(cls.load(folder))
                except Exception:
                    pass
        return projects

    def save(self):
        tmp = os.path.join(self.folder, self.FILE + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, os.path.join(self.folder, self.FILE))

    def delete(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    # ---- puntos ----
    def new_point(self, lat, lon, accuracy=None, when=None):
        """Crea un punto (aun no guardado)."""
        when = when or datetime.now()
        return {
            "id": None,
            "lat": float(lat),
            "lon": float(lon),
            "precision_m": accuracy,
            "fecha": when.strftime(DATE_FMT),
            "valores": {c: "" for c in self.columns},
            "fotos": [],
        }

    def save_point(self, point):
        if point["id"] is None:
            point["id"] = self.data["siguiente_id"]
            self.data["siguiente_id"] += 1
            self.points.append(point)
        else:
            for i, p in enumerate(self.points):
                if p["id"] == point["id"]:
                    self.points[i] = point
                    break
        self.save()
        return point

    def delete_point(self, point_id):
        keep = []
        for p in self.points:
            if p["id"] == point_id:
                for rel in p["fotos"]:
                    try:
                        os.remove(os.path.join(self.folder, rel))
                    except OSError:
                        pass
            else:
                keep.append(p)
        self.data["puntos"] = keep
        self.save()

    def photo_path(self, rel):
        return os.path.join(self.folder, rel)

    def add_photo(self, point, source_path, font_path=None):
        """Copia la foto al proyecto con marca de agua. Devuelve la ruta relativa."""
        if len(point["fotos"]) >= MAX_PHOTOS:
            raise ValueError("Maximo %d fotos por punto." % MAX_PHOTOS)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        rel = os.path.join("fotos", "foto_%s.jpg" % stamp)
        self.photos_dir  # crea la carpeta
        lines = [
            "Lat: %s   Lon: %s" % (format_coord(point["lat"]), format_coord(point["lon"])),
            CRS_LABEL,
            "Fecha: %s" % datetime.now().strftime(DATE_FMT),
            "Proyecto: %s" % self.name,
        ]
        watermark_image(source_path, os.path.join(self.folder, rel), lines, font_path)
        point["fotos"].append(rel)
        return rel

    def remove_photo(self, point, rel):
        if rel in point["fotos"]:
            point["fotos"].remove(rel)
        try:
            os.remove(os.path.join(self.folder, rel))
        except OSError:
            pass


# --------------------------------------------------------------------------
# Marca de agua
# --------------------------------------------------------------------------
def _load_font(font_path, size):
    if font_path and os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antiguo
        return ImageFont.load_default()


def watermark_image(src, dst, lines, font_path=None, max_side=None):
    """Abre src, corrige la orientacion y escribe las lineas en un cuadro
    oscuro en la esquina inferior derecha. Por defecto conserva la resolucion
    original (max_side=None). La primera linea (coordenadas) va en amarillo."""
    img = Image.open(src)
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max_side and max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    w, h = img.size

    # El cuadro ocupa cerca del 62% del lado corto: se lee bien sin tapar la foto.
    probe = _load_font(font_path, 100)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    widest = max(tmp.textbbox((0, 0), ln, font=probe)[2] for ln in lines) or 1
    size = max(16, int(100 * (min(w, h) * 0.62) / widest))
    font = _load_font(font_path, size)
    stroke = max(2, size // 12)

    draw = ImageDraw.Draw(img, "RGBA")
    pad = int(size * 0.5)
    gap = int(size * 0.25)
    boxes = [draw.textbbox((0, 0), ln, font=font, stroke_width=stroke) for ln in lines]
    line_h = max(b[3] - b[1] for b in boxes)
    block_w = max(b[2] - b[0] for b in boxes) + 2 * pad
    block_h = len(lines) * line_h + (len(lines) - 1) * gap + 2 * pad
    margin = int(min(w, h) * 0.02)
    x0, y0 = w - block_w - margin, h - block_h - margin
    draw.rounded_rectangle([x0, y0, w - margin, h - margin], radius=pad,
                           fill=(0, 0, 0, 190))
    y = y0 + pad
    for i, (ln, b) in enumerate(zip(lines, boxes)):
        color = (255, 230, 0, 255) if i == 0 else (255, 255, 255, 255)
        draw.text((x0 + pad - b[0], y - b[1]), ln, font=font, fill=color,
                  stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        y += line_h + gap
    img.save(dst, "JPEG", quality=92)
    return dst


# --------------------------------------------------------------------------
# Registro fotografico en PDF
# --------------------------------------------------------------------------
def _wrap(draw, text, font, max_w):
    words, out, cur = text.split(), [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if draw.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            out.append(cur)
            cur = wd
    if cur:
        out.append(cur)
    return out or [""]


def _header_page(photo, header_lines, font_path, title_idx=0):
    """Devuelve una imagen con una franja blanca de encabezado arriba y la foto
    debajo, sin cambiar la resolucion de la foto."""
    w = photo.width
    size = max(18, int(w * 0.03))
    font_b = _load_font(font_path, size)
    font_r = _load_font(font_path, int(size * 0.85))
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    pad = int(size * 0.8)
    rows = []
    for i, ln in enumerate(header_lines):
        f = font_b if i == title_idx else font_r
        for part in _wrap(tmp, ln, f, w - 2 * pad):
            rows.append((part, f, i == title_idx))
    row_h = int(size * 1.35)
    head_h = 2 * pad + row_h * len(rows)
    page = Image.new("RGB", (w, head_h + photo.height), (255, 255, 255))
    d = ImageDraw.Draw(page)
    y = pad
    for text, f, is_title in rows:
        d.text((pad, y), text, font=f, fill=(16, 42, 67) if is_title else (40, 40, 40))
        y += row_h
    d.line([(pad, head_h - 4), (w - pad, head_h - 4)], fill=(31, 111, 139), width=max(2, size // 8))
    page.paste(photo, (0, head_h))
    return page


def export_photo_pdf(project, out_path, font_path=None, page_width_in=8.27):
    """Registro fotografico: portada y una pagina por foto, con el punto, la
    coordenada, la fecha y el valor de la primera columna. Las fotos van a su
    resolucion original. Las paginas se agregan una por una para no llenar la
    memoria del telefono."""
    first_col = project.columns[0] if project.columns else None
    n_photos = sum(len(p["fotos"]) for p in project.points)

    cover = Image.new("RGB", (1240, 1754), (255, 255, 255))
    d = ImageDraw.Draw(cover)
    ft = _load_font(font_path, 64)
    fr = _load_font(font_path, 36)
    y = 220
    for ln in _wrap(d, "Registro fotografico", ft, 1040):
        d.text((100, y), ln, font=ft, fill=(16, 42, 67)); y += 84
    for ln in _wrap(d, project.name, ft, 1040):
        d.text((100, y), ln, font=ft, fill=(31, 111, 139)); y += 84
    y += 40
    for ln in ["Puntos: %d" % len(project.points), "Fotos: %d" % n_photos,
               "Sistema de coordenadas: " + CRS_LABEL,
               "Generado: %s" % datetime.now().strftime(DATE_FMT)]:
        d.text((100, y), ln, font=fr, fill=(60, 60, 60)); y += 56
    cover.save(out_path, "PDF", resolution=150.0)

    for p in project.points:
        header = ["Punto %d" % p["id"]]
        if first_col:
            header.append("%s: %s" % (first_col, p["valores"].get(first_col, "") or "-"))
        header.append("Lat: %s   Lon: %s   (%s)" % (format_coord(p["lat"]), format_coord(p["lon"]), CRS_LABEL))
        header.append("Fecha: %s" % p["fecha"])
        fotos = [r for r in p["fotos"] if os.path.exists(project.photo_path(r))]
        if not fotos:
            blank = Image.new("RGB", (1240, 300), (245, 245, 245))
            ImageDraw.Draw(blank).text((60, 120), "Sin fotos", font=_load_font(font_path, 40), fill=(120, 120, 120))
            page = _header_page(blank, header, font_path)
            page.save(out_path, "PDF", resolution=page.width / page_width_in, append=True)
            continue
        for j, rel in enumerate(fotos):
            with Image.open(project.photo_path(rel)) as im:
                photo = im.convert("RGB")
            lines = list(header)
            lines[0] = "Punto %d  -  Foto %d de %d" % (p["id"], j + 1, len(fotos))
            page = _header_page(photo, lines, font_path)
            del photo
            page.save(out_path, "PDF", resolution=page.width / page_width_in, append=True, quality=92)
            del page
    return out_path


# --------------------------------------------------------------------------
# Exportacion a Excel
# --------------------------------------------------------------------------
def export_excel(project, out_path, thumb_px=220):
    """Hoja 1: datos. Hoja 2: mismos datos + fotos en columnas a la derecha."""
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    headers = ["N°"] + FIXED_COLUMNS + list(project.columns)
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1F6F8B")

    def row_values(p):
        vals = [p["id"], round(p["lat"], 7), round(p["lon"], 7), p["fecha"]]
        vals += [p["valores"].get(c, "") for c in project.columns]
        return vals

    def write_header(ws, cols):
        ws.append(cols)
        for i in range(1, len(cols) + 1):
            cell = ws.cell(row=1, column=i)
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.freeze_panes = "A2"

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Datos"
    write_header(ws1, headers)
    for p in project.points:
        ws1.append(row_values(p))
    for i, col in enumerate(headers, start=1):
        width = max([len(str(col))] + [len(str(ws1.cell(row=r, column=i).value or ""))
                                        for r in range(2, ws1.max_row + 1)])
        ws1.column_dimensions[get_column_letter(i)].width = min(60, max(10, width + 2))
    for r in range(2, ws1.max_row + 1):
        ws1.cell(row=r, column=2).number_format = "0.0000000"
        ws1.cell(row=r, column=3).number_format = "0.0000000"

    ws2 = wb.create_sheet("Datos con fotos")
    photo_headers = ["Foto_%d" % (i + 1) for i in range(MAX_PHOTOS)]
    write_header(ws2, headers + photo_headers)
    first_photo_col = len(headers) + 1
    tmp_files = []
    row_h_pt = thumb_px * 0.75 + 6
    col_w = thumb_px / 7.0 + 2
    for i in range(1, len(headers) + 1):
        ws2.column_dimensions[get_column_letter(i)].width = ws1.column_dimensions[get_column_letter(i)].width
    for j in range(MAX_PHOTOS):
        ws2.column_dimensions[get_column_letter(first_photo_col + j)].width = col_w

    thumbs_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)), ".miniaturas_tmp")
    os.makedirs(thumbs_dir, exist_ok=True)
    for r, p in enumerate(project.points, start=2):
        for c, val in enumerate(row_values(p), start=1):
            cell = ws2.cell(row=r, column=c, value=val)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws2.cell(row=r, column=2).number_format = "0.0000000"
        ws2.cell(row=r, column=3).number_format = "0.0000000"
        has_photo = False
        for j, rel in enumerate(p["fotos"][:MAX_PHOTOS]):
            src = project.photo_path(rel)
            if not os.path.exists(src):
                continue
            thumb = os.path.join(thumbs_dir, "t_%d_%d.jpg" % (p["id"], j))
            with Image.open(src) as im:
                im = im.convert("RGB")
                im.thumbnail((thumb_px, thumb_px), Image.LANCZOS)
                im.save(thumb, "JPEG", quality=85)
            tmp_files.append(thumb)
            xl_img = XLImage(thumb)
            ws2.add_image(xl_img, "%s%d" % (get_column_letter(first_photo_col + j), r))
            has_photo = True
        if has_photo:
            ws2.row_dimensions[r].height = row_h_pt

    wb.save(out_path)  # openpyxl lee las imagenes aqui; despues se pueden borrar
    shutil.rmtree(thumbs_dir, ignore_errors=True)
    return out_path
