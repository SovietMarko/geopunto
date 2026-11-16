# Geopunto

App Android hecha con Python + Kivy para tomar coordenadas en campo
(EPSG:4326 - WGS 84), llenar una tabla de datos por punto, tomar hasta 5 fotos
con marca de agua y exportar todo a Excel.

## Qué hace

1. **Proyecto**: pide el nombre del proyecto y lo guarda en el teléfono. Los
   proyectos aparecen en la pantalla de inicio para volver a abrirlos.
2. **Tabla**: eliges cuántas columnas de datos quieres y si usas nombres
   estándar (`dato_1`, `dato_2`, ..., `dato_n`) o los escribes tú. Las columnas
   `Latitud`, `Longitud` y `Fecha` siempre se agregan con esos nombres.
3. **Mapa**: muestra el mapa híbrido de Google (también satélite, calles u
   OpenStreetMap) con tu posición GPS (punto azul) y los puntos guardados
   (marcadores rojos; tócalos para editarlos).
4. **Tomar punto aquí**: guarda la coordenada GPS actual y abre un formulario
   con una casilla por cada columna, más botones para **Cámara** y **Galería**
   (máximo 5 fotos). Cada foto recibe una marca de agua con latitud, longitud
   (EPSG:4326 - WGS 84), fecha y hora, y el nombre del proyecto.
   Si aún no hay señal GPS puedes esperar o usar el centro del mapa (+).
5. **Exportar Excel**: crea un `.xlsx` con
   - Hoja 1 `Datos`: N°, Latitud, Longitud, Fecha y tus columnas.
   - Hoja 2 `Datos con fotos`: lo mismo, con las fotos en las columnas
     `Foto_1` ... `Foto_5` a la derecha.
   El archivo queda en **Documentos/Geopunto** del teléfono y el botón
   **Compartir** permite enviarlo por WhatsApp, correo, Drive, etc.

## Archivos

| Archivo | Para qué |
|---|---|
| `main.py` | Interfaz (pantallas, mapa, GPS, formulario) |
| `geodata.py` | Proyectos, marca de agua (Pillow) y exportación (openpyxl) |
| `android_bridge.py` | Permisos, cámara, galería, guardar en Documentos y compartir |
| `assets/` | Icono (planeta), pantalla de carga y marcadores |
| `buildozer.spec` | Configuración para compilar el APK |
| `.github/workflows/build-apk.yml` | Compila el APK gratis en GitHub |
| `tests/` | Pruebas de la lógica |

## Cómo obtener el APK

### Opción A: GitHub (no necesitas Linux)
1. Crea un repositorio en GitHub y sube todo el contenido de esta carpeta
   (incluida la carpeta oculta `.github`).
2. Ve a la pestaña **Actions**; la compilación arranca sola (o pulsa
   *Run workflow*). La primera vez tarda unos 30 a 40 minutos.
3. Al terminar, descarga **geopunto-apk** en la sección *Artifacts*, descomprime
   e instala el `.apk` en el teléfono (permite "instalar apps desconocidas").

### Opción B: en tu PC con Linux o WSL2 (Windows)
```bash
sudo apt install -y git zip unzip openjdk-17-jdk python3-pip autoconf automake \
     libtool pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev cmake libffi-dev libssl-dev
pip install --user --upgrade buildozer "cython<3.1"
cd geopunto
buildozer -v android debug          # el APK queda en bin/
buildozer android deploy run logcat # opcional: instalar con el teléfono conectado por USB
```

## Probar en la PC (sin compilar)
```bash
pip install -r requirements-desktop.txt
python main.py        # sin GPS: usa el centro del mapa; "Cámara" abre un selector de archivos
python -m pytest tests
```

## Notas
- Al abrir por primera vez, acepta los permisos de **ubicación** y **cámara**.
- El mapa necesita internet; las coordenadas vienen del GPS y funcionan sin datos.
  Los mosaicos que ya viste quedan guardados en caché.
- Las capas de Google se cargan directo desde sus servidores de mosaicos, algo
  que los términos de Google no permiten formalmente. Para uso personal suele
  funcionar; si algún día deja de cargar, cambia a OpenStreetMap en el selector.
- Las fotos se reducen a 2048 px por lado para que el proyecto y el Excel no
  pesen demasiado.
