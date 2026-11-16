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
