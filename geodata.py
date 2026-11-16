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


def watermark_image(src, dst, lines, font_path=None, max_side=2048):
    """Abre src, corrige la orientacion, reduce a max_side y escribe las lineas
    de texto sobre una franja semitransparente en la esquina inferior."""
    img = Image.open(src)
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    w, h = img.size
    size = max(14, int(min(w, h) * 0.035))
    font = _load_font(font_path, size)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    pad = int(size * 0.6)
    gap = int(size * 0.3)
    boxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
    line_h = max(b[3] - b[1] for b in boxes)
    block_w = max(b[2] - b[0] for b in boxes) + 2 * pad
    block_h = len(lines) * line_h + (len(lines) - 1) * gap + 2 * pad
    x0, y0 = 0, h - block_h
    draw.rectangle([x0, y0, min(w, block_w), h], fill=(0, 0, 0, 150))
    y = y0 + pad
    for ln, b in zip(lines, boxes):
        draw.text((x0 + pad + 2, y - b[1] + 2), ln, font=font, fill=(0, 0, 0, 255))
        draw.text((x0 + pad, y - b[1]), ln, font=font, fill=(255, 235, 59, 255))
        y += line_h + gap
    out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    out.save(dst, "JPEG", quality=88)
    return dst


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
