[app]
title = Geopunto
package.name = geopunto
package.domain = org.campo
source.dir = .
source.include_exts = py,png,jpg,kv,ttf
source.exclude_dirs = tests, tools, bin, .buildozer, .github
version = 1.0.0

# Librerias que se empaquetan en el APK
requirements = python3,kivy==2.3.1,filetype,plyer,pillow,openpyxl,et_xmlfile,mapview,requests,urllib3,charset_normalizer==3.3.2,chardet,idna,certifi,androidstorage4kivy

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #102A43
orientation = portrait
fullscreen = 0

android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, CAMERA, (name=android.permission.WRITE_EXTERNAL_STORAGE;maxSdkVersion=28), (name=android.permission.READ_EXTERNAL_STORAGE;maxSdkVersion=32)
android.api = 34
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
android.allow_backup = True
p4a.branch = master

[buildozer]
log_level = 2
warn_on_root = 1
