# -*- coding: utf-8 -*-
"""Geopunto: toma coordenadas en campo (EPSG:4326 - WGS 84), datos y fotos
con marca de agua, y exporta todo a Excel."""
import copy
import os
import threading
from datetime import datetime

import kivy
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from kivy_garden.mapview import MapMarker, MapSource, MapView

import android_bridge as droid
import geodata
from geodata import FIXED_COLUMNS, MAX_PHOTOS, Project, format_coord

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(APP_DIR, "assets")
WATERMARK_FONT = os.path.join(os.path.dirname(kivy.__file__), "data", "fonts", "Roboto-Bold.ttf")

# Capas de mapa. Google: lyrs=y hibrido, s satelite, m calles.
MAP_LAYERS = {
    "Google Hibrido": ("https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", "google_y", 21, "© Google"),
    "Google Satelite": ("https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", "google_s", 21, "© Google"),
    "Google Mapa": ("https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", "google_m", 21, "© Google"),
    "OpenStreetMap": ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "osm", 19, "© OpenStreetMap"),
}
DEFAULT_LAYER = "Google Hibrido"

KV = r"""
#:import dp kivy.metrics.dp
#:set C_BAR (0.08, 0.27, 0.35, 1)
#:set C_ACC (0.12, 0.44, 0.55, 1)
#:set C_OK (0.18, 0.55, 0.30, 1)
#:set C_BG (0.95, 0.96, 0.97, 1)

<Label>:
    color: 0.1, 0.1, 0.12, 1

<Button>:
    color: 1, 1, 1, 1

<NameToggle@ToggleButton>:
    background_normal: ''
    background_down: ''
    background_color: (0.18, 0.55, 0.30, 1) if self.state == 'down' else (0.6, 0.62, 0.65, 1)

<AppButton@Button>:
    background_normal: ''
    background_color: C_ACC
    color: 1, 1, 1, 1
    font_size: '16sp'
    bold: True
    size_hint_y: None
    height: dp(52)

<Field@TextInput>:
    multiline: False
    size_hint_y: None
    height: dp(46)
    font_size: '16sp'
    padding: dp(10), dp(12)
    write_tab: False

<TopBar@BoxLayout>:
    title: ''
    show_back: True
    size_hint_y: None
    height: dp(56)
    padding: dp(6), 0
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: C_BAR
        Rectangle:
            pos: self.pos
            size: self.size
    Button:
        text: '<'
        font_size: '24sp'
        bold: True
        size_hint_x: None
        width: dp(48) if root.show_back else 0
        opacity: 1 if root.show_back else 0
        disabled: not root.show_back
        background_normal: ''
        background_color: 0, 0, 0, 0
        color: 1, 1, 1, 1
        on_release: app.go_back()
    Label:
        text: root.title
        color: 1, 1, 1, 1
        bold: True
        font_size: '19sp'
        halign: 'left'
        valign: 'middle'
        text_size: self.size
        shorten: True
        shorten_from: 'right'

<Screen>:
    canvas.before:
        Color:
            rgba: C_BG
        Rectangle:
            pos: self.pos
            size: self.size

<HomeScreen>:
    BoxLayout:
        orientation: 'vertical'
        TopBar:
            title: 'Geopunto'
            show_back: False
        BoxLayout:
            orientation: 'vertical'
            padding: dp(14)
            spacing: dp(10)
            Image:
                source: app.icon
                size_hint_y: None
                height: dp(110)
            AppButton:
                text: '+  Nuevo proyecto'
                background_color: C_OK
                on_release: app.open_screen('new')
            Label:
                text: 'Proyectos guardados'
                bold: True
                size_hint_y: None
                height: dp(30)
                text_size: self.size
                halign: 'left'
            ScrollView:
                GridLayout:
                    id: project_list
                    cols: 1
                    spacing: dp(6)
                    size_hint_y: None
                    height: self.minimum_height

<NewProjectScreen>:
    BoxLayout:
        orientation: 'vertical'
        TopBar:
            title: 'Nuevo proyecto'
        ScrollView:
            BoxLayout:
                orientation: 'vertical'
                padding: dp(14)
                spacing: dp(8)
                size_hint_y: None
                height: self.minimum_height
                Label:
                    text: 'Nombre del proyecto'
                    size_hint_y: None
                    height: dp(26)
                    text_size: self.size
                    halign: 'left'
                Field:
                    id: name
                    hint_text: 'Ej: Levantamiento finca norte'
                Label:
                    text: 'Cantidad de columnas de datos (ademas de Latitud, Longitud y Fecha)'
                    size_hint_y: None
                    height: dp(44)
                    text_size: self.width, None
                    halign: 'left'
                Field:
                    id: ncols
                    text: '3'
                    input_filter: 'int'
                    on_text: root.rebuild_names()
                Label:
                    text: 'Nombres de las columnas'
                    size_hint_y: None
                    height: dp(26)
                    text_size: self.size
                    halign: 'left'
                BoxLayout:
                    size_hint_y: None
                    height: dp(46)
                    spacing: dp(6)
                    NameToggle:
                        id: std
                        text: 'Estandar (dato_1...)'
                        group: 'names'
                        state: 'down'
                        allow_no_selection: False
                        on_state: root.rebuild_names()
                    NameToggle:
                        id: custom
                        text: 'Personalizados'
                        group: 'names'
                        allow_no_selection: False
                        on_state: root.rebuild_names()
                GridLayout:
                    id: names_box
                    cols: 1
                    spacing: dp(6)
                    size_hint_y: None
                    height: self.minimum_height
                Label:
                    id: preview
                    size_hint_y: None
                    height: self.texture_size[1] + dp(12)
                    text_size: self.width, None
                    color: 0.3, 0.3, 0.35, 1
                    font_size: '13sp'
                AppButton:
                    text: 'Crear proyecto'
                    background_color: C_OK
                    on_release: root.create()

<MapScreen>:
    BoxLayout:
        orientation: 'vertical'
        TopBar:
            title: app.project.name if app.project else ''
        BoxLayout:
            size_hint_y: None
            height: dp(42)
            padding: dp(4)
            spacing: dp(4)
            Spinner:
                id: layer
                text: app.default_layer
                values: app.layer_names
                on_text: root.set_layer(self.text)
            Button:
                text: 'Centrar en mi'
                size_hint_x: 0.6
                on_release: root.center_on_me()
        RelativeLayout:
            MapView:
                id: map
                zoom: 17
                lat: 4.6
                lon: -74.08
                double_tap_zoom: True
            Label:
                text: '+'
                font_size: '28sp'
                color: 1, 1, 1, 0.8
                opacity: 1 if root.show_cross else 0
                pos_hint: {'center_x': 0.5, 'center_y': 0.5}
                size_hint: None, None
                size: dp(30), dp(30)
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: dp(176)
            padding: dp(8)
            spacing: dp(6)
            canvas.before:
                Color:
                    rgba: 1, 1, 1, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
            Label:
                text: root.status_text
                markup: True
                font_size: '14sp'
                text_size: self.size
                halign: 'left'
                valign: 'middle'
            AppButton:
                text: 'Tomar punto aqui'
                background_color: C_OK
                on_release: root.take_point()
            BoxLayout:
                size_hint_y: None
                height: dp(48)
                spacing: dp(6)
                AppButton:
                    height: dp(48)
                    text: 'Puntos (%d)' % root.n_points
                    on_release: app.open_screen('points')
                AppButton:
                    height: dp(48)
                    text: 'Excel'
                    on_release: app.export_excel()
                AppButton:
                    height: dp(48)
                    text: 'PDF fotos'
                    on_release: app.export_pdf()

<PointScreen>:
    BoxLayout:
        orientation: 'vertical'
        TopBar:
            title: root.title
        ScrollView:
            BoxLayout:
                orientation: 'vertical'
                padding: dp(12)
                spacing: dp(6)
                size_hint_y: None
                height: self.minimum_height
                Label:
                    text: root.header_text
                    markup: True
                    size_hint_y: None
                    height: self.texture_size[1] + dp(14)
                    text_size: self.width, None
                    font_size: '15sp'
                    canvas.before:
                        Color:
                            rgba: 0.86, 0.92, 0.94, 1
                        Rectangle:
                            pos: self.pos
                            size: self.size
                GridLayout:
                    id: fields
                    cols: 1
                    spacing: dp(4)
                    size_hint_y: None
                    height: self.minimum_height
                Label:
                    text: 'Fotos (%d de %d)  -  toca una foto para quitarla' % (root.n_photos, root.max_photos)
                    bold: True
                    size_hint_y: None
                    height: dp(34)
                    text_size: self.size
                    halign: 'left'
                    valign: 'bottom'
                GridLayout:
                    id: photos
                    cols: 3
                    spacing: dp(4)
                    size_hint_y: None
                    height: self.minimum_height
                    row_default_height: dp(110)
                    row_force_default: True
                BoxLayout:
                    size_hint_y: None
                    height: dp(52)
                    spacing: dp(6)
                    AppButton:
                        text: 'Camara'
                        disabled: root.n_photos >= root.max_photos or root.busy
                        on_release: root.add_photo(camera=True)
                    AppButton:
                        text: 'Galeria'
                        disabled: root.n_photos >= root.max_photos or root.busy
                        on_release: root.add_photo(camera=False)
                Label:
                    size_hint_y: None
                    height: dp(8)
        BoxLayout:
            size_hint_y: None
            height: dp(64)
            padding: dp(6)
            spacing: dp(6)
            AppButton:
                text: 'Cancelar'
                background_color: 0.55, 0.55, 0.58, 1
                on_release: root.cancel()
            AppButton:
                text: 'Guardar punto'
                background_color: C_OK
                disabled: root.busy
                on_release: root.save()

<PointsScreen>:
    BoxLayout:
        orientation: 'vertical'
        TopBar:
            title: 'Puntos guardados'
        ScrollView:
            GridLayout:
                id: plist
                cols: 1
                padding: dp(8)
                spacing: dp(6)
                size_hint_y: None
                height: self.minimum_height
"""


# ---------------------------------------------------------------------------
# Utilidades de interfaz
# ---------------------------------------------------------------------------
def message(title, text, buttons=(("Aceptar", None),)):
    box = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(10))
    lbl = Label(text=text, color=(1, 1, 1, 1), halign="left", valign="top")
    lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
    box.add_widget(lbl)
    row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
    popup = Popup(title=title, content=box, size_hint=(0.92, None), height=dp(280),
                  auto_dismiss=False)
    for label, cb in buttons:
        b = Button(text=label)

        def _press(_btn, cb=cb):
            popup.dismiss()
            if cb:
                cb()
        b.bind(on_release=_press)
        row.add_widget(b)
    box.add_widget(row)
    popup.open()
    return popup


def busy_popup(text):
    p = Popup(title="Geopunto", content=Label(text=text, color=(1, 1, 1, 1)),
              size_hint=(0.8, None), height=dp(160), auto_dismiss=False)
    p.open()
    return p


class PhotoThumb(ButtonBehavior, Image):
    rel = StringProperty("")


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------
class HomeScreen(Screen):
    def on_pre_enter(self, *a):
        app = App.get_running_app()
        box = self.ids.project_list
        box.clear_widgets()
        projects = Project.list_all(app.projects_dir)
        if not projects:
            box.add_widget(Label(text="Aun no hay proyectos.", size_hint_y=None, height=dp(40),
                                 color=(0.4, 0.4, 0.45, 1)))
        for p in projects:
            row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(6))
            b = Button(text="%s\n[size=12sp]%d puntos  -  %d columnas[/size]" % (
                p.name, len(p.points), len(p.columns)), markup=True, halign="left",
                background_normal="", background_color=(1, 1, 1, 1), color=(0.1, 0.1, 0.12, 1))
            b.bind(size=lambda w, s: setattr(w, "text_size", (s[0] - dp(20), None)))
            b.bind(on_release=lambda _b, folder=p.folder: app.open_project(folder))
            d = Button(text="Borrar", size_hint_x=None, width=dp(80),
                       background_normal="", background_color=(0.75, 0.25, 0.25, 1))
            d.bind(on_release=lambda _b, proj=p: self.ask_delete(proj))
            row.add_widget(b)
            row.add_widget(d)
            box.add_widget(row)

    def ask_delete(self, proj):
        def _do():
            proj.delete()
            self.on_pre_enter()
        message("Borrar proyecto", 'Se borrara "%s" con todos sus puntos y fotos.\n'
                'Exporta el Excel antes si lo necesitas.' % proj.name,
                (("Cancelar", None), ("Borrar", _do)))


class NewProjectScreen(Screen):
    def on_pre_enter(self, *a):
        self.ids.name.text = ""
        self.ids.ncols.text = "3"
        self.ids.std.state = "down"
        self.ids.custom.state = "normal"
        self.rebuild_names()

    def _n(self):
        try:
            return max(0, min(50, int(self.ids.ncols.text or 0)))
        except ValueError:
            return 0

    def rebuild_names(self, *a):
        box = self.ids.names_box
        old = [w.text for w in reversed(box.children)]
        box.clear_widgets()
        n = self._n()
        if self.ids.custom.state == "down":
            for i in range(n):
                f = Factory_Field()
                f.hint_text = "Columna %d (vacio = dato_%d)" % (i + 1, i + 1)
                if i < len(old):
                    f.text = old[i]
                f.bind(text=lambda *a: self.update_preview())
                box.add_widget(f)
        self.update_preview()

    def custom_names(self):
        if self.ids.custom.state != "down":
            return None
        return [w.text for w in reversed(self.ids.names_box.children)]

    def update_preview(self):
        n = self._n()
        try:
            cols = geodata.build_column_names(n, self.custom_names()) if n else []
            self.ids.preview.text = "Tabla: " + ", ".join(FIXED_COLUMNS + cols)
        except ValueError as e:
            self.ids.preview.text = "[!] %s" % e

    def create(self):
        app = App.get_running_app()
        try:
            cols = geodata.build_column_names(self._n(), self.custom_names())
            project = Project.create(app.projects_dir, self.ids.name.text, cols)
        except ValueError as e:
            message("Revisa los datos", str(e))
            return
        app.open_project(project.folder, replace_history=True)


def Factory_Field():
    from kivy.factory import Factory
    return Factory.Field()


class MapScreen(Screen):
    status_text = StringProperty("Buscando senal GPS...")
    n_points = NumericProperty(0)
    show_cross = BooleanProperty(False)

    def on_kv_post(self, *a):
        self.gps_marker = None
        self.point_markers = []
        self._centered_once = False

    def on_pre_enter(self, *a):
        app = App.get_running_app()
        self.n_points = len(app.project.points)
        self.refresh_markers()
        self.update_status()
        if not self._centered_once and app.project.points:
            last = app.project.points[-1]
            self.ids.map.center_on(last["lat"], last["lon"])

    def set_layer(self, name):
        app = App.get_running_app()
        url, key, maxz, attrib = MAP_LAYERS[name]
        self.ids.map.map_source = MapSource(url=url, cache_key=key, max_zoom=maxz,
                                            subdomains="0123", image_ext="jpg" if "google" in key else "png",
                                            attribution=attrib, cache_dir=app.cache_dir)

    def refresh_markers(self):
        mv = self.ids.map
        for m in self.point_markers:
            mv.remove_marker(m)
        self.point_markers = []
        for p in App.get_running_app().project.points:
            m = MapMarker(lat=p["lat"], lon=p["lon"], source=os.path.join(ASSETS, "marker_point.png"))
            m.bind(on_release=lambda _m, pid=p["id"]: App.get_running_app().edit_point(pid))
            mv.add_marker(m)
            self.point_markers.append(m)

    def on_gps(self, lat, lon, accuracy):
        mv = self.ids.map
        if self.gps_marker is None:
            self.gps_marker = MapMarker(lat=lat, lon=lon, anchor_y=0.5,
                                        source=os.path.join(ASSETS, "marker_gps.png"))
            mv.add_marker(self.gps_marker)
        else:
            self.gps_marker.lat, self.gps_marker.lon = lat, lon
            mv.trigger_update(False)
        if not self._centered_once:
            self._centered_once = True
            mv.center_on(lat, lon)
        self.update_status()

    def update_status(self):
        app = App.get_running_app()
        if app.gps_fix:
            lat, lon, acc = app.gps_fix
            acc_txt = (" (+/- %.0f m)" % acc) if acc else ""
            self.status_text = ("[b]Lat:[/b] %s   [b]Lon:[/b] %s%s\n[size=12sp]EPSG:4326 - WGS 84[/size]"
                                % (format_coord(lat), format_coord(lon), acc_txt))
            self.show_cross = False
        elif not droid.IS_ANDROID:
            self.status_text = "PC sin GPS: se usara el centro del mapa (+)\n[size=12sp]EPSG:4326 - WGS 84[/size]"
            self.show_cross = True
        else:
            self.status_text = "Buscando senal GPS...  " + (app.gps_status or "")

    def center_on_me(self):
        app = App.get_running_app()
        if app.gps_fix:
            self.ids.map.center_on(app.gps_fix[0], app.gps_fix[1])
        else:
            message("GPS", "Todavia no hay posicion GPS. Sal a cielo abierto y espera unos segundos.")

    def take_point(self):
        app = App.get_running_app()
        if app.gps_fix:
            lat, lon, acc = app.gps_fix
            app.new_point(lat, lon, acc)
            return
        mv = self.ids.map

        def _use_center():
            app.new_point(mv.lat, mv.lon, None)
        if droid.IS_ANDROID:
            self.show_cross = True
            message("Sin senal GPS", "Aun no hay posicion GPS.\nPuedes esperar o usar el centro del mapa (+).",
                    (("Esperar", None), ("Usar centro", _use_center)))
        else:
            _use_center()


class PointScreen(Screen):
    title = StringProperty("Nuevo punto")
    header_text = StringProperty("")
    n_photos = NumericProperty(0)
    max_photos = NumericProperty(MAX_PHOTOS)
    busy = BooleanProperty(False)

    def load(self, project, point, is_new):
        self.project = project
        self.point = copy.deepcopy(point)
        self.is_new = is_new
        self._added = []
        self._removed = []
        self.title = "Nuevo punto" if is_new else "Punto %d" % point["id"]
        acc = point.get("precision_m")
        self.header_text = ("[b]Latitud:[/b] %s\n[b]Longitud:[/b] %s\n[b]Fecha:[/b] %s%s\n"
                            "[size=12sp]EPSG:4326 - WGS 84[/size]" % (
                                format_coord(point["lat"]), format_coord(point["lon"]), point["fecha"],
                                ("\n[b]Precision:[/b] +/- %.0f m" % acc) if acc else ""))
        box = self.ids.fields
        box.clear_widgets()
        self.inputs = {}
        for col in project.columns:
            box.add_widget(Label(text=col, bold=True, size_hint_y=None, height=dp(26),
                                 halign="left", text_size=(Window.width - dp(24), None)))
            ti = TextInput(text=str(self.point["valores"].get(col, "")), multiline=False,
                           size_hint_y=None, height=dp(46), font_size="16sp", write_tab=False,
                           padding=(dp(10), dp(12)))
            box.add_widget(ti)
            self.inputs[col] = ti
        self.refresh_photos()

    def refresh_photos(self):
        grid = self.ids.photos
        grid.clear_widgets()
        for rel in self.point["fotos"]:
            t = PhotoThumb(source=self.project.photo_path(rel), rel=rel, nocache=True, fit_mode="contain")
            t.bind(on_release=lambda w: self.ask_remove_photo(w.rel))
            grid.add_widget(t)
        self.n_photos = len(self.point["fotos"])

    def add_photo(self, camera=True):
        if self.n_photos >= MAX_PHOTOS:
            return
        self.busy = True
        if camera:
            droid.take_photo(self._got_photo)
        else:
            droid.pick_image(self._got_photo)

    def _got_photo(self, path):
        if not path:
            self.busy = False
            return
        popup = busy_popup("Agregando marca de agua...")

        def work():
            err = None
            try:
                rel = self.project.add_photo(self.point, path, WATERMARK_FONT)
                self._added.append(rel)
            except Exception as e:  # noqa
                err = str(e)
            finally:
                if droid.IS_ANDROID:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            self._photo_done(popup, err)
        threading.Thread(target=work, daemon=True).start()

    @mainthread
    def _photo_done(self, popup, err):
        popup.dismiss()
        self.busy = False
        if err:
            message("Error con la foto", err)
        self.refresh_photos()

    def ask_remove_photo(self, rel):
        def _do():
            if rel in self._added:
                self.project.remove_photo(self.point, rel)
                self._added.remove(rel)
            else:
                self.point["fotos"].remove(rel)
                self._removed.append(rel)
            self.refresh_photos()
        message("Quitar foto", "Quitar esta foto del punto?", (("No", None), ("Quitar", _do)))

    def save(self):
        for col, ti in self.inputs.items():
            self.point["valores"][col] = ti.text.strip()
        for rel in self._removed:
            try:
                os.remove(self.project.photo_path(rel))
            except OSError:
                pass
        self._added, self._removed = [], []
        self.project.save_point(self.point)
        App.get_running_app().go_back()

    def cancel(self):
        for rel in list(self._added):
            self.project.remove_photo(self.point, rel)
        self._added, self._removed = [], []
        App.get_running_app().go_back()


class PointsScreen(Screen):
    def on_pre_enter(self, *a):
        app = App.get_running_app()
        box = self.ids.plist
        box.clear_widgets()
        pts = list(reversed(app.project.points))
        if not pts:
            box.add_widget(Label(text="Aun no hay puntos.", size_hint_y=None, height=dp(40)))
        for p in pts:
            first = ", ".join("%s: %s" % (c, p["valores"].get(c, "")) for c in app.project.columns[:2])
            row = BoxLayout(size_hint_y=None, height=dp(66), spacing=dp(6))
            b = Button(text="[b]Punto %d[/b]  -  %s  -  %d fotos\n[size=12sp]%s, %s   %s[/size]" % (
                p["id"], p["fecha"], len(p["fotos"]), format_coord(p["lat"]), format_coord(p["lon"]), first),
                markup=True, halign="left", background_normal="", background_color=(1, 1, 1, 1),
                color=(0.1, 0.1, 0.12, 1))
            b.bind(size=lambda w, s: setattr(w, "text_size", (s[0] - dp(16), None)))
            b.bind(on_release=lambda _b, pid=p["id"]: app.edit_point(pid))
            d = Button(text="Borrar", size_hint_x=None, width=dp(76),
                       background_normal="", background_color=(0.75, 0.25, 0.25, 1))
            d.bind(on_release=lambda _b, pid=p["id"]: self.ask_delete(pid))
            row.add_widget(b)
            row.add_widget(d)
            box.add_widget(row)

    def ask_delete(self, pid):
        app = App.get_running_app()

        def _do():
            app.project.delete_point(pid)
            self.on_pre_enter()
        message("Borrar punto", "Borrar el punto %d y sus fotos?" % pid, (("No", None), ("Borrar", _do)))


# ---------------------------------------------------------------------------
# Aplicacion
# ---------------------------------------------------------------------------
class GeopuntoApp(App):
    project = ObjectProperty(None, allownone=True)
    gps_fix = ObjectProperty(None, allownone=True)
    gps_status = StringProperty("")
    default_layer = StringProperty(DEFAULT_LAYER)
    layer_names = list(MAP_LAYERS.keys())

    def build(self):
        self.title = "Geopunto"
        self.icon = os.path.join(ASSETS, "icon.png")
        base = self.user_data_dir
        self.projects_dir = os.path.join(base, "proyectos")
        self.export_dir = os.path.join(base, "exportados")
        self.cache_dir = os.path.join(base, "cache_mapa")
        for d in (self.projects_dir, self.export_dir, self.cache_dir):
            os.makedirs(d, exist_ok=True)
        self.history = []
        Builder.load_string(KV)
        self.sm = ScreenManager(transition=NoTransition())
        self.sm.add_widget(HomeScreen(name="home"))
        self.sm.add_widget(NewProjectScreen(name="new"))
        self.sm.add_widget(MapScreen(name="map"))
        self.sm.add_widget(PointScreen(name="point"))
        self.sm.add_widget(PointsScreen(name="points"))
        Window.bind(on_keyboard=self._on_key)
        Window.softinput_mode = "below_target"
        return self.sm

    def on_start(self):
        droid.request_permissions(self._permissions_done)

    def _permissions_done(self, ok):
        self.start_gps()
        droid.keep_screen_on(True)

    # ----- GPS -----
    def start_gps(self):
        if not droid.IS_ANDROID:
            return
        try:
            from plyer import gps
            gps.configure(on_location=self._on_location, on_status=self._on_gps_status)
            gps.start(minTime=1000, minDistance=0)
            self._gps = gps
        except Exception as e:
            self.gps_status = "GPS no disponible: %s" % e

    @mainthread
    def _on_location(self, **kw):
        lat, lon = kw.get("lat"), kw.get("lon")
        if lat is None or lon is None:
            return
        self.gps_fix = (float(lat), float(lon), kw.get("accuracy"))
        self.sm.get_screen("map").on_gps(*self.gps_fix)

    @mainthread
    def _on_gps_status(self, stype, status):
        self.gps_status = "%s" % status
        if self.sm.current == "map":
            self.sm.get_screen("map").update_status()

    def on_pause(self):
        try:
            self._gps.stop()
        except Exception:
            pass
        return True

    def on_resume(self):
        try:
            self._gps.start(minTime=1000, minDistance=0)
        except Exception:
            pass

    # ----- Navegacion -----
    def open_screen(self, name, replace_history=False):
        if not replace_history:
            self.history.append(self.sm.current)
        self.sm.current = name

    def go_back(self):
        if self.sm.current == "point":
            # salir del formulario sin guardar descarta las fotos nuevas
            scr = self.sm.get_screen("point")
            if scr._added:
                return message("Salir sin guardar", "Hay fotos sin guardar. Descartar el punto?",
                               (("No", None), ("Descartar", scr.cancel)))
        if self.history:
            self.sm.current = self.history.pop()
            return True
        return False

    def _on_key(self, window, key, *a):
        if key == 27:  # boton atras de Android / Esc
            if self.sm.current == "home":
                return False
            self.go_back()
            return True
        return False

    # ----- Proyectos y puntos -----
    def open_project(self, folder, replace_history=False):
        self.project = Project.load(folder)
        if replace_history:
            self.history = ["home"]
            self.sm.current = "map"
        else:
            self.open_screen("map")
        self.sm.get_screen("map").set_layer(self.sm.get_screen("map").ids.layer.text)

    def new_point(self, lat, lon, acc):
        point = self.project.new_point(lat, lon, acc, datetime.now())
        self.sm.get_screen("point").load(self.project, point, True)
        self.open_screen("point")

    def edit_point(self, pid):
        for p in self.project.points:
            if p["id"] == pid:
                self.sm.get_screen("point").load(self.project, p, False)
                self.open_screen("point")
                return

    def export_excel(self):
        self._export("xlsx", "Generando Excel...", geodata.export_excel,
                     "Excel listo", "Hoja 1: Datos\nHoja 2: Datos con fotos")

    def export_pdf(self):
        if not any(p["fotos"] for p in (self.project.points if self.project else [])):
            message("Registro fotografico", "El proyecto no tiene fotos todavia.")
            return
        self._export("pdf", "Generando PDF de fotos...\n(puede tardar con muchas fotos)",
                     lambda proj, out: geodata.export_photo_pdf(proj, out, WATERMARK_FONT),
                     "PDF listo", "Una pagina por foto con punto, coordenada,\nfecha y %s." % (
                         self.project.columns[0] if self.project.columns else "datos"))

    def _export(self, ext, busy_text, func, title, detail):
        if not self.project.points:
            message("Exportar", "El proyecto no tiene puntos todavia.")
            return
        popup = busy_popup(busy_text)
        name = "%s_%s.%s" % (geodata.slugify(self.project.name), datetime.now().strftime("%Y%m%d_%H%M%S"), ext)
        out = os.path.join(self.export_dir, name)

        def work():
            err = None
            try:
                func(self.project, out)
            except Exception as e:  # noqa
                err = str(e)
            self._export_done(popup, out, err, title, detail)
        threading.Thread(target=work, daemon=True).start()

    @mainthread
    def _export_done(self, popup, out, err, title, detail):
        popup.dismiss()
        if err:
            message("Error al exportar", err)
            return
        where, uri = droid.save_to_shared(out)
        text = "Archivo: %s\nGuardado en: %s\n\n%s" % (os.path.basename(out), where, detail)
        buttons = [("Aceptar", None)]
        if uri is not None:
            buttons.append(("Compartir", lambda: droid.share_file(uri)))
        message(title, text, buttons)


if __name__ == "__main__":
    GeopuntoApp().run()
