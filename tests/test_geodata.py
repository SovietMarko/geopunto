"""Pruebas de la logica (ejecutar: python -m pytest tests)."""
import os
import sys

import pytest
from openpyxl import load_workbook
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import geodata  # noqa: E402


def make_photo(path, size=(3000, 4000), exif_rotate=False):
    img = Image.new("RGB", size, (90, 140, 60))
    exif = None
    if exif_rotate:
        exif = img.getexif()
        exif[0x0112] = 6  # rotar 90
    img.save(path, "JPEG", exif=exif) if exif else img.save(path, "JPEG")
    return path


def test_column_names():
    assert geodata.build_column_names(3) == ["dato_1", "dato_2", "dato_3"]
    assert geodata.build_column_names(3, ["Especie", "", "Altura"]) == ["Especie", "dato_2", "Altura"]
    with pytest.raises(ValueError):
        geodata.build_column_names(2, ["Latitud", "x"])
    with pytest.raises(ValueError):
        geodata.build_column_names(2, ["a", "A"])


def test_full_flow(tmp_path):
    base = tmp_path / "proyectos"
    proj = geodata.Project.create(str(base), "Finca Ñandú", ["Especie", "Altura"])
    with pytest.raises(ValueError):
        geodata.Project.create(str(base), "Finca Ñandú", ["x"])
    p = proj.new_point(4.6097102, -74.0817500, 4.5)
    p["valores"]["Especie"] = "Roble"
    for i in range(5):
        src = make_photo(str(tmp_path / ("src%d.jpg" % i)), exif_rotate=(i == 0))
        proj.add_photo(p, src)
    with pytest.raises(ValueError):
        proj.add_photo(p, src)
    proj.save_point(p)
    p2 = proj.new_point(4.61, -74.08)
    proj.save_point(p2)

    again = geodata.Project.load(proj.folder)
    assert len(again.points) == 2 and again.points[0]["id"] == 1 and again.points[1]["id"] == 2
    first = Image.open(again.photo_path(again.points[0]["fotos"][0]))
    assert first.size == (4000, 3000)  # resolucion original, girada segun EXIF

    out = str(tmp_path / "salida.xlsx")
    geodata.export_excel(again, out)
    wb = load_workbook(out)
    assert wb.sheetnames == ["Datos", "Datos con fotos"]
    ws1, ws2 = wb["Datos"], wb["Datos con fotos"]
    assert [c.value for c in ws1[1]] == ["N°", "Latitud", "Longitud", "Fecha", "Especie", "Altura"]
    assert ws1.cell(row=2, column=2).value == pytest.approx(4.6097102)
    assert ws1.cell(row=2, column=5).value == "Roble"
    assert [c.value for c in ws2[1]][-5:] == ["Foto_1", "Foto_2", "Foto_3", "Foto_4", "Foto_5"]
    assert len(ws2._images) == 5
    assert not os.path.exists(str(tmp_path / ".miniaturas_tmp"))

    again.delete_point(1)
    assert len(geodata.Project.load(proj.folder).points) == 1
    assert os.listdir(again.photos_dir) == []


def test_photo_pdf(tmp_path):
    proj = geodata.Project.create(str(tmp_path), "PDF", ["Especie"])
    p = proj.new_point(4.6, -74.08)
    p["valores"]["Especie"] = "Roble"
    proj.add_photo(p, make_photo(str(tmp_path / "a.jpg"), size=(1200, 1600)))
    proj.add_photo(p, make_photo(str(tmp_path / "b.jpg"), size=(1600, 1200)))
    proj.save_point(p)
    proj.save_point(proj.new_point(4.61, -74.09))
    out = str(tmp_path / "r.pdf")
    geodata.export_photo_pdf(proj, out)
    data = open(out, "rb").read()
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 4 or data.count(b"/Page") >= 4


def test_average_fixes():
    s = [(4.0, -74.0, 4.0, 2600.0), (4.00001, -74.00001, 4.0, 2601.0), (4.01, -74.01, 40.0, 2700.0)]
    lat, lon, acc, alt, n = geodata.average_fixes(s)
    assert n == 2  # la lectura de 40 m se descarta
    assert lat == pytest.approx(4.000005) and lon == pytest.approx(-74.000005)
    assert acc == 4.0 and alt == pytest.approx(2600.5)


def test_export_gis(tmp_path):
    import io, json, zipfile
    import shapefile
    proj = geodata.Project.create(str(tmp_path), "Finca Ñandú", ["Especie arbórea", "Especie arbórea 2"])
    p = proj.new_point(4.6097102, -74.08175, 3.2, altitude=2600, samples=8)
    p["valores"]["Especie arbórea"] = "Roble"
    proj.save_point(p)
    out = str(tmp_path / "sig.zip")
    geodata.export_gis(proj, out)
    zf = zipfile.ZipFile(out)
    names = set(zf.namelist())
    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".geojson", ".kml", ".csv"):
        assert "Finca_Nandu" + ext in names
    r = shapefile.Reader(shp=io.BytesIO(zf.read("Finca_Nandu.shp")), shx=io.BytesIO(zf.read("Finca_Nandu.shx")),
                         dbf=io.BytesIO(zf.read("Finca_Nandu.dbf")), encoding="utf-8")
    assert r.shape(0).points[0] == pytest.approx([-74.08175, 4.6097102])
    fields = [f[0] for f in r.fields[1:]]
    assert len(set(fields)) == len(fields) and all(len(f) <= 10 for f in fields)
    assert "Roble" in list(r.record(0))
    gj = json.loads(zf.read("Finca_Nandu.geojson"))
    assert gj["features"][0]["properties"]["Especie arbórea"] == "Roble"


def test_nmea_diagnostico(monkeypatch):
    """El diagnostico de satelites lee sentencias NMEA reales (sin Kivy en pantalla)."""
    pytest.importorskip("kivy")
    import android_bridge as ab
    monkeypatch.setattr(ab, "IS_ANDROID", True)
    r = ab.GPSReader(lambda *a: None)
    r.started, r.nmea_ok, r.t_start = True, True, ab.time.time() - 100
    monkeypatch.setattr(r, "has_precise_permission", lambda: True)
    monkeypatch.setattr(r, "gps_enabled", lambda: True)
    assert "No se ve ningun satelite" in r.hint()
    r._on_nmea("$GPGSV,3,1,10,02,45,120,30,05,60,010,28,07,20,200,25,09,15,300,20*7D\r\n")
    r._on_nmea("$GLGSV,2,1,06,65,40,100,22,66,30,200,20,67,10,050,18,68,50,300,25*4B")
    assert r.sats() == (16, 0)
    assert "Se ven 16 satelites" in r.hint()
    r._on_nmea("$GNGGA,123519,0436.582,N,07404.905,W,1,07,1.2,2600.0,M,0.0,M,,*5A")
    assert r.sats() == (16, 7) and r.hint() == ""
    assert "16 vistos, 7 usados" in r.diag_text()
