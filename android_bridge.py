# -*- coding: utf-8 -*-
"""Todo lo especifico de Android: permisos, camara, galeria, almacenamiento
compartido y compartir archivos. En PC estas funciones no hacen nada o usan
alternativas para poder probar la app."""
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.utils import platform

IS_ANDROID = platform == "android"

REQ_CAMERA = 4301
REQ_GALLERY = 4302
RESULT_OK = -1

_pending = {}  # request_code -> (callback, uri_de_camara)


def request_permissions(callback=None):
    if not IS_ANDROID:
        if callback:
            callback(True)
        return
    from android.permissions import Permission, request_permissions as _req
    perms = [Permission.ACCESS_FINE_LOCATION, Permission.ACCESS_COARSE_LOCATION,
             Permission.CAMERA]
    if _sdk_int() <= 28:
        perms += [Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE]

    def _done(permissions, grants):
        if callback:
            Clock.schedule_once(lambda dt: callback(all(grants)))
    _req(perms, _done)


def _sdk_int():
    from jnius import autoclass
    return autoclass("android.os.Build$VERSION").SDK_INT


def _activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


_bound = False


def _bind_activity_result():
    global _bound
    if _bound:
        return
    from android import activity
    activity.bind(on_activity_result=_on_activity_result)
    _bound = True


def _on_activity_result(request_code, result_code, intent):
    if request_code not in _pending:
        return
    callback, camera_uri = _pending.pop(request_code)
    path = None
    try:
        if result_code == RESULT_OK:
            uri = camera_uri if request_code == REQ_CAMERA else (intent.getData() if intent else None)
            if uri is not None:
                path = _copy_uri_to_private(uri)
                if request_code == REQ_CAMERA:
                    # La foto original (sin marca) se borra de la galeria; la
                    # version con marca de agua queda en la app y en el Excel.
                    try:
                        _activity().getContentResolver().delete(uri, None, None)
                    except Exception:
                        pass
        elif request_code == REQ_CAMERA and camera_uri is not None:
            _activity().getContentResolver().delete(camera_uri, None, None)
    except Exception as exc:
        Logger.exception("Geopunto: error leyendo la foto: %s" % exc)
    Clock.schedule_once(lambda dt: callback(path))


def _copy_uri_to_private(uri):
    """Copia un content:// a un archivo privado de la app y devuelve su ruta."""
    from androidstorage4kivy import SharedStorage
    return SharedStorage().copy_from_shared(uri)


def take_photo(callback):
    """Abre la camara del telefono. callback(ruta_jpg o None)."""
    if not IS_ANDROID:
        return pick_image(callback)
    from jnius import autoclass, cast
    _bind_activity_result()
    Intent = autoclass("android.content.Intent")
    MediaStore = autoclass("android.provider.MediaStore")
    Media = autoclass("android.provider.MediaStore$Images$Media")
    ContentValues = autoclass("android.content.ContentValues")
    from datetime import datetime
    values = ContentValues()
    values.put("_display_name", "geopunto_%s.jpg" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    values.put("mime_type", "image/jpeg")
    if _sdk_int() >= 29:
        values.put("relative_path", "Pictures/Geopunto")
    resolver = _activity().getContentResolver()
    uri = resolver.insert(Media.EXTERNAL_CONTENT_URI, values)
    intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
    intent.putExtra(MediaStore.EXTRA_OUTPUT, cast("android.os.Parcelable", uri))
    intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION)
    _pending[REQ_CAMERA] = (callback, uri)
    _activity().startActivityForResult(intent, REQ_CAMERA)


def pick_image(callback):
    """Elige una imagen de la galeria (Android) o del disco (PC)."""
    if IS_ANDROID:
        from jnius import autoclass
        _bind_activity_result()
        Intent = autoclass("android.content.Intent")
        intent = Intent(Intent.ACTION_GET_CONTENT)
        intent.setType("image/*")
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        _pending[REQ_GALLERY] = (callback, None)
        _activity().startActivityForResult(intent, REQ_GALLERY)
        return
    _desktop_file_chooser(callback)


def _desktop_file_chooser(callback):
    import os
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.popup import Popup
    box = BoxLayout(orientation="vertical", spacing=6)
    chooser = FileChooserListView(path=os.path.expanduser("~"),
                                  filters=["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"])
    row = BoxLayout(size_hint_y=None, height="48dp", spacing=6)
    ok = Button(text="Usar imagen")
    cancel = Button(text="Cancelar")
    row.add_widget(cancel)
    row.add_widget(ok)
    box.add_widget(chooser)
    box.add_widget(row)
    popup = Popup(title="Elegir imagen", content=box, size_hint=(0.95, 0.95))

    def _ok(*_):
        popup.dismiss()
        callback(chooser.selection[0] if chooser.selection else None)
    ok.bind(on_release=_ok)
    cancel.bind(on_release=lambda *_: (popup.dismiss(), callback(None)))
    popup.open()


def save_to_shared(path):
    """Copia el archivo a Documentos/Geopunto del telefono. Devuelve
    (texto_para_mostrar, uri_para_compartir)."""
    if not IS_ANDROID:
        return path, None
    try:
        from androidstorage4kivy import SharedStorage
        uri = SharedStorage().copy_to_shared(path)
        return "Documentos/Geopunto", uri
    except Exception as exc:
        Logger.exception("Geopunto: no se pudo copiar a Documentos: %s" % exc)
        return path, None


def share_file(uri):
    if not IS_ANDROID or uri is None:
        return False
    try:
        from androidstorage4kivy import ShareSheet
        ShareSheet().share_file(uri)
        return True
    except Exception as exc:
        Logger.exception("Geopunto: no se pudo compartir: %s" % exc)
        return False


def keep_screen_on(on=True):
    if not IS_ANDROID:
        return
    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass
        WindowManager = autoclass("android.view.WindowManager$LayoutParams")

        @run_on_ui_thread
        def _set():
            window = _activity().getWindow()
            if on:
                window.addFlags(WindowManager.FLAG_KEEP_SCREEN_ON)
            else:
                window.clearFlags(WindowManager.FLAG_KEEP_SCREEN_ON)
        _set()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# GPS
# ---------------------------------------------------------------------------
# Se usa el receptor GPS satelital directamente (proveedor "gps"), que funciona
# sin datos moviles ni wifi. El proveedor "network" solo se usa, si existe, para
# una primera posicion aproximada mientras llegan los satelites.
class GPSReader(object):
    """callback(lat, lon, accuracy_m, provider, altitude). status_cb(texto)."""

    def __init__(self, callback, status_cb=None):
        self.callback = callback
        self.status_cb = status_cb or (lambda t: None)
        self._lm = None
        self._listener = None
        self.started = False

    def _status(self, text):
        Clock.schedule_once(lambda dt: self.status_cb(text))

    def has_precise_permission(self):
        if not IS_ANDROID:
            return True
        try:
            return _activity().checkSelfPermission("android.permission.ACCESS_FINE_LOCATION") == 0
        except Exception:
            return True

    def gps_enabled(self):
        if not IS_ANDROID or self._lm is None:
            return True
        try:
            return bool(self._lm.isProviderEnabled("gps"))
        except Exception:
            return True

    def start(self):
        if not IS_ANDROID or self.started:
            return
        from jnius import autoclass, java_method, PythonJavaClass
        reader = self

        class _Listener(PythonJavaClass):
            __javainterfaces__ = ["android/location/LocationListener"]

            @java_method("(Landroid/location/Location;)V")
            def onLocationChanged(self, loc):
                reader._deliver(loc)

            @java_method("(Ljava/util/List;)V", name="onLocationChanged")
            def onLocationChangedList(self, locs):  # API 31+: lote de posiciones
                try:
                    for i in range(locs.size()):
                        reader._deliver(locs.get(i))
                except Exception:
                    pass

            @java_method("(I)V")
            def onFlushComplete(self, code):
                pass

            @java_method("(Ljava/lang/String;)V")
            def onProviderEnabled(self, provider):
                if provider == "gps":
                    reader._status("GPS activado, esperando satelites...")

            @java_method("(Ljava/lang/String;)V")
            def onProviderDisabled(self, provider):
                if provider == "gps":
                    reader._status("El GPS del telefono esta apagado")

            @java_method("(Ljava/lang/String;ILandroid/os/Bundle;)V")
            def onStatusChanged(self, provider, status, extras):
                pass

        Context = autoclass("android.content.Context")
        Looper = autoclass("android.os.Looper")
        self._lm = _activity().getSystemService(Context.LOCATION_SERVICE)
        self._listener = _Listener()
        ok = False
        for provider, min_time in (("gps", 1000), ("network", 5000)):
            try:
                if self._lm.getProvider(provider) is None:
                    continue
                self._lm.requestLocationUpdates(provider, min_time, 0.0, self._listener,
                                                Looper.getMainLooper())
                ok = ok or provider == "gps"
            except Exception as exc:
                Logger.warning("Geopunto: proveedor %s no disponible: %s" % (provider, exc))
        # posicion previa (si existe) para no empezar de cero
        try:
            last = self._lm.getLastKnownLocation("gps")
            if last is not None:
                self._deliver(last, stale=True)
        except Exception:
            pass
        self.started = True
        if not ok:
            self._status("No se pudo iniciar el GPS (revisa permisos de ubicacion precisa)")
        elif not self.gps_enabled():
            self._status("El GPS del telefono esta apagado")
        else:
            self._status("Esperando satelites (al aire libre, sin datos puede tardar 1-3 min)")

    def _deliver(self, loc, stale=False):
        try:
            acc = float(loc.getAccuracy()) if loc.hasAccuracy() else None
            alt = float(loc.getAltitude()) if loc.hasAltitude() else None
            data = (float(loc.getLatitude()), float(loc.getLongitude()), acc,
                    "cache" if stale else str(loc.getProvider()), alt)
        except Exception as exc:
            Logger.warning("Geopunto: posicion invalida: %s" % exc)
            return
        Clock.schedule_once(lambda dt: self.callback(*data))

    def stop(self):
        if self._lm is not None and self._listener is not None:
            try:
                self._lm.removeUpdates(self._listener)
            except Exception:
                pass
        self.started = False


def open_location_settings():
    if not IS_ANDROID:
        return
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        _activity().startActivity(Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))
    except Exception:
        pass
