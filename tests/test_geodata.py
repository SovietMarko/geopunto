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
    assert first.size == (2048, 1536)  # reducida y girada segun EXIF

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
