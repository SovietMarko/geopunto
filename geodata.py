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


def average_fixes(samples):
    """Promedia lecturas GPS [(lat, lon, precision_m, altitud_m), ...].

    Se ponderan por 1/precision^2 (las lecturas mas precisas pesan mas) y se
    descartan las que tienen el doble de error que la mejor. Devuelve
    (lat, lon, precision_estimada_m, altitud_m, n_usadas)."""
    if not samples:
        raise ValueError("No hay lecturas GPS.")
    accs = [s[2] for s in samples if s[2]]
    best = min(accs) if accs else None
    used = [s for s in samples if not best or not s[2] or s[2] <= max(2 * best, best + 3)]
    wsum = lat = lon = 0.0
    alt_w = alt = 0.0
    for la, lo, acc, al in used:
        w = 1.0 / max(acc or 10.0, 1.0) ** 2
        wsum += w
        lat += la * w
        lon += lo * w
        if al is not None:
            alt += al * w
            alt_w += w
    used_acc = sorted(s[2] for s in used if s[2])
    est = used_acc[len(used_acc) // 2] if used_acc else None  # mediana: estimacion prudente
    return (lat / wsum, lon / wsum, est, (alt / alt_w) if alt_w else None, len(used))


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
    def new_point(self, lat, lon, accuracy=None, when=None, altitude=None, samples=1):
        """Crea un punto (aun no guardado)."""
        when = when or datetime.now()
        return {
            "id": None,
            "lat": float(lat),
            "lon": float(lon),
            "precision_m": None if accuracy is None else round(float(accuracy), 1),
            "altitud_m": None if altitude is None else round(float(altitude), 1),
            "muestras": int(samples),
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


def _grid_layout(sizes, box_w, box_h, gap):
    """Elige filas x columnas que dan la mayor area de foto en el recuadro."""
    n = len(sizes)
    best = None
    for cols in range(1, n + 1):
        rows = (n + cols - 1) // cols
        cw = (box_w - gap * (cols - 1)) / float(cols)
        ch = (box_h - gap * (rows - 1)) / float(rows)
        area = 0.0
        for (w, h) in sizes:
            sc = min(cw / w, ch / h)
            area += w * sc * h * sc
        if best is None or area > best[0] + 1:
            best = (area, cols, rows, cw, ch)
    return best[1:]


def export_photo_pdf(project, out_path, font_path=None, dpi=250):
    """Registro fotografico: portada y una hoja A4 por punto con todas sus
    fotos. El tamano de cada foto depende de cuantas tenga el punto (1 foto
    ocupa casi toda la hoja; 5 fotos se reparten en una cuadricula). Las hojas
    se agregan una por una para no llenar la memoria del telefono."""
    W, H = int(8.27 * dpi), int(11.69 * dpi)
    margin = int(0.45 * dpi)
    first_col = project.columns[0] if project.columns else None
    n_photos = sum(len(p["fotos"]) for p in project.points)
    blue, dark, grey = (16, 42, 67), (40, 40, 40), (110, 110, 110)

    cover = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(cover)
    ft = _load_font(font_path, int(dpi * 0.42))
    fr = _load_font(font_path, int(dpi * 0.2))
    y = int(H * 0.18)
    for ln in _wrap(d, "Registro fotografico", ft, W - 2 * margin):
        d.text((margin, y), ln, font=ft, fill=blue); y += int(dpi * 0.55)
    for ln in _wrap(d, project.name, ft, W - 2 * margin):
        d.text((margin, y), ln, font=ft, fill=(31, 111, 139)); y += int(dpi * 0.55)
    y += int(dpi * 0.3)
    for ln in ["Puntos: %d" % len(project.points), "Fotos: %d" % n_photos,
               "Sistema de coordenadas: " + CRS_LABEL,
               "Generado: %s" % datetime.now().strftime(DATE_FMT)]:
        d.text((margin, y), ln, font=fr, fill=dark); y += int(dpi * 0.32)
    cover.save(out_path, "PDF", resolution=float(dpi))
    del cover

    f_title = _load_font(font_path, int(dpi * 0.2))
    f_text = _load_font(font_path, int(dpi * 0.14))
    f_small = _load_font(font_path, int(dpi * 0.1))
    for p in project.points:
        page = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(page)
        y = margin
        d.text((margin, y), "Punto %d" % p["id"], font=f_title, fill=blue)
        y += int(dpi * 0.3)
        lines = []
        if first_col:
            lines.append("%s: %s" % (first_col, p["valores"].get(first_col, "") or "-"))
        lines.append("Latitud: %s    Longitud: %s" % (format_coord(p["lat"]), format_coord(p["lon"])))
        extra = CRS_LABEL
        if p.get("precision_m"):
            extra += "    Precision: +/- %.1f m" % p["precision_m"]
        lines.append(extra)
        lines.append("Fecha: %s" % p["fecha"])
        for ln in lines:
            for part in _wrap(d, ln, f_text, W - 2 * margin):
                d.text((margin, y), part, font=f_text, fill=dark)
                y += int(dpi * 0.2)
        y += int(dpi * 0.05)
        d.line([(margin, y), (W - margin, y)], fill=(31, 111, 139), width=max(2, dpi // 60))
        y += int(dpi * 0.15)

        fotos = [r for r in p["fotos"] if os.path.exists(project.photo_path(r))]
        box_top, box_bottom = y, H - margin - int(dpi * 0.15)
        if not fotos:
            d.text((margin, box_top + int(dpi * 0.3)), "Sin fotos", font=f_text, fill=grey)
        else:
            sizes = []
            for rel in fotos:
                with Image.open(project.photo_path(rel)) as im:
                    sizes.append(im.size)
            gap = int(dpi * 0.12)
            label_h = int(dpi * 0.16)
            box_w, box_h = W - 2 * margin, box_bottom - box_top
            cols, rows, cw, ch = _grid_layout([(w, h + label_h) for w, h in sizes], box_w, box_h, gap)
            for k, rel in enumerate(fotos):
                r, c = divmod(k, cols)
                cx = margin + c * (cw + gap)
                cy = box_top + r * (ch + gap)
                with Image.open(project.photo_path(rel)) as im:
                    sc = min(cw / im.width, (ch - label_h) / im.height)
                    tw, th = max(1, int(im.width * sc)), max(1, int(im.height * sc))
                    im.draft("RGB", (tw, th))  # decodifica reducido: menos memoria
                    ph = im.convert("RGB").resize((tw, th), Image.LANCZOS)
                px = int(cx + (cw - tw) / 2)
                page.paste(ph, (px, int(cy)))
                del ph
                d.text((px, int(cy) + th + int(dpi * 0.02)), "Foto %d" % (k + 1), font=f_small, fill=grey)
        d.text((margin, H - margin), "%s  -  Punto %d" % (project.name, p["id"]), font=f_small, fill=grey)
        page.save(out_path, "PDF", resolution=float(dpi), append=True, quality=90)
        del page
    return out_path


# --------------------------------------------------------------------------
# Exportacion para SIG (QGIS / ArcGIS)
# --------------------------------------------------------------------------
WGS84_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,'
             '298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')


def _dbf_names(names):
    """Nombres de campo validos para DBF: ASCII, max 10 caracteres, unicos."""
    out, used = [], set()
    for n in names:
        base = re.sub(r"[^A-Za-z0-9_]", "_", unicodedata.normalize("NFKD", n)
                      .encode("ascii", "ignore").decode()).strip("_") or "campo"
        if base[0].isdigit():
            base = "c_" + base
        base = base[:10]
        cand, i = base, 1
        while cand.lower() in used:
            suf = "_%d" % i
            cand = base[:10 - len(suf)] + suf
            i += 1
        used.add(cand.lower())
        out.append(cand)
    return out


def _gis_rows(project):
    rows = []
    for p in project.points:
        rec = {"id": p["id"], "latitud": round(p["lat"], 7), "longitud": round(p["lon"], 7),
               "fecha": p["fecha"], "precision": p.get("precision_m"),
               "altitud": p.get("altitud_m"), "n_fotos": len(p["fotos"]),
               "fotos": ";".join(os.path.basename(f) for f in p["fotos"])}
        for c in project.columns:
            rec[c] = p["valores"].get(c, "")
        rows.append(rec)
    return rows


def export_gis(project, out_zip):
    """ZIP con la capa de puntos en EPSG:4326 para QGIS / ArcGIS:
    Shapefile (.shp .shx .dbf .prj .cpg), GeoJSON, KML y CSV."""
    import csv
    import io
    import zipfile
    import shapefile  # pyshp

    base = slugify(project.name)
    fixed = ["id", "latitud", "longitud", "fecha", "precision", "altitud", "n_fotos", "fotos"]
    keys = fixed + list(project.columns)
    rows = _gis_rows(project)

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        # --- Shapefile ---
        shp, shx, dbf = io.BytesIO(), io.BytesIO(), io.BytesIO()
        w = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POINT, encoding="utf-8")
        dbf_names = _dbf_names(keys)
        for k, dn in zip(keys, dbf_names):
            if k in ("id", "n_fotos"):
                w.field(dn, "N", 10, 0)
            elif k in ("latitud", "longitud"):
                w.field(dn, "N", 14, 7)
            elif k in ("precision", "altitud"):
                w.field(dn, "N", 10, 1)
            else:
                w.field(dn, "C", 254)
        for r in rows:
            w.point(r["longitud"], r["latitud"])
            w.record(*[r[k] if r[k] is not None else (None if k in ("precision", "altitud") else "")
                       for k in keys])
        w.close()
        zf.writestr(base + ".shp", shp.getvalue())
        zf.writestr(base + ".shx", shx.getvalue())
        zf.writestr(base + ".dbf", dbf.getvalue())
        zf.writestr(base + ".prj", WGS84_PRJ)
        zf.writestr(base + ".cpg", "UTF-8")
        if any(dn != k for k, dn in zip(keys, dbf_names)):
            zf.writestr(base + "_campos_shapefile.txt", "Nombre en el shapefile -> nombre original\n" +
                        "\n".join("%s -> %s" % (dn, k) for k, dn in zip(keys, dbf_names)))

        # --- GeoJSON ---
        gj = {"type": "FeatureCollection", "name": base,
              "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
              "features": [{"type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [r["longitud"], r["latitud"]]},
                            "properties": {k: r[k] for k in keys}} for r in rows]}
        zf.writestr(base + ".geojson", json.dumps(gj, ensure_ascii=False, indent=1))

        # --- KML (Google Earth) ---
        from xml.sax.saxutils import escape
        pm = []
        for r in rows:
            data = "".join('<Data name="%s"><value>%s</value></Data>' % (escape(str(k)), escape(str(r[k] if r[k] is not None else "")))
                           for k in keys)
            pm.append("<Placemark><name>Punto %s</name><ExtendedData>%s</ExtendedData>"
                      "<Point><coordinates>%s,%s,0</coordinates></Point></Placemark>"
                      % (r["id"], data, r["longitud"], r["latitud"]))
        kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">'
               "<Document><name>%s</name>%s</Document></kml>" % (escape(project.name), "".join(pm)))
        zf.writestr(base + ".kml", kml)

        # --- CSV (X = longitud, Y = latitud) ---
        buf = io.StringIO()
        cw = csv.writer(buf)
        cw.writerow(keys)
        for r in rows:
            cw.writerow(["" if r[k] is None else r[k] for k in keys])
        zf.writestr(base + ".csv", "\ufeff" + buf.getvalue())

        zf.writestr("LEEME.txt", (
            "Proyecto: %s\nSistema de coordenadas: %s\nPuntos: %d\n\n"
            "QGIS: arrastra el .shp o el .geojson al mapa.\n"
            "ArcGIS: agrega el .shp (Add Data).\n"
            "Google Earth: abre el .kml.\n"
            "CSV: X = longitud, Y = latitud, EPSG:4326.\n") % (project.name, CRS_LABEL, len(rows)))
    return out_zip


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
