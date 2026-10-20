# Documento de Contexto y Especificación Técnica
# Proyecto: Spotify to YouTube Music (STFY to YTM)

Este documento contiene la descripción completa de arquitectura, funcionamiento, decisiones de diseño, peculiaridades de las APIs y el prompt maestro detallado para que cualquier agente de inteligencia artificial o desarrollador pueda entender, auditar, corregir o recrear completamente la aplicación desde cero.

---

## 1. Visión General del Proyecto

**STFY to YTM** es una solución integral y gratuita para transferir y sincronizar playlists desde **Spotify** hacia **YouTube Music**, sin requerir cuentas de Spotify Premium ni configuraciones complejas de desarrollador en Spotify.

El proyecto cuenta con dos implementaciones independientes y complementarias que comparten los mismos principios y algoritmos:
1. **Script CLI Monolítico (`spotify_to_ytm.py`)**: Script ejecutable por terminal en cualquier sistema operativo.
2. **Aplicación Web y Contenedor Docker (`web/`)**: Aplicación web moderna basada en Flask, Gunicorn y Bootstrap 5, lista para ejecutarse en Docker o en un servidor Linux Debian con Apache (`mod_wsgi`).

---

## 2. Arquitectura del Sistema

### 2.1. Estructura de Directorios

```text
spotify-to-ytm/
├── spotify_to_ytm.py             # Script de terminal interactivo (CLI)
├── README.md                     # Documentación para usuarios
├── Contexto.md                   # Este documento de especificación completa
├── .gitignore                    # Exclusiones de Git (tokens, cookies, logs)
└── web/                          # Paquete de la aplicación Web y Docker
    ├── app.py                    # Servidor Flask, endpoints API REST y enrutamiento
    ├── wsgi.py                   # Punto de entrada WSGI para Gunicorn / Apache
    ├── requirements.txt          # Dependencias Python (Flask, ytmusicapi, spotdl, requests, etc.)
    ├── Dockerfile                # Imagen ligera (python:3.11-slim) con healthcheck nativo
    ├── docker-compose.yml        # Configuración de Docker Compose (puerto 5000:5000)
    ├── MANUAL_DEBIAN_APACHE.md   # Guía paso a paso para despliegue en Debian con Apache mod_wsgi
    ├── core/                     # Módulos del motor backend
    │   ├── normalizer.py         # Normalización de títulos y fuzzy matching de canciones
    │   ├── spotify_reader.py     # Lectura de Spotify (Scraping SSR, perfiles y parseo CSV)
    │   ├── ytm_engine.py         # Conexión YTM, búsqueda multietapa, chunking y simulación
    │   └── job_runner.py         # Ejecución asíncrona en segundo plano con hilos y logs en vivo
    ├── templates/
    │   └── index.html            # Interfaz de usuario SPA en modo oscuro (Bootstrap 5)
    ├── static/
    │   ├── css/
    │   │   └── style.css         # Estilos visuales personalizados
    │   └── js/
    │       └── app.js            # Lógica cliente JavaScript (reactividad, polling, toasts)
    ├── deploy/                   # Plantillas para Apache VirtualHost y servicios systemd
    ├── data/                     # Almacenamiento de credenciales (headers_auth.json, oauth.json)
    ├── reports/                  # Informes CSV generados tras transferencias
    └── uploads/                  # Subida temporal de archivos CSV
```

---

## 3. Módulos y Lógica del Motor Backend (`web/core/`)

### 3.1. Normalización y Coincidencia Difusa (`core/normalizer.py`)
YouTube Music y Spotify titulan las canciones de manera dispar (presencia de etiquetas `(Remastered 2021)`, `[Official Music Video]`, `feat. Artista`, o formato `Artista - Título`).
* **`limpiar_cadena(texto)`**: Convierte a minúsculas, elimina tildes/acentos y caracteres no alfanuméricos.
* **`normalizar(titulo)`**: Utiliza expresiones regulares para suprimir sufijos innecesarios (`(feat. ...)`, `[video oficial]`, `remastered`, `lyrics`, `live`, etc.).
* **`coincide(clave_a, clave_b, raw_a, raw_b)`**:
  - Aplica comparación estricta de tuplas normalizadas `(titulo_limpio, artista_limpio)`.
  - Si no coincide exactamente, aplica `difflib.SequenceMatcher(None, tit_a, tit_b).ratio() >= 0.82` o inclusión de subcadenas mayores a 4 caracteres.
  - Genera candidatos desglosando títulos que contienen guiones (`Artista - Título`) para probar combinaciones invertidas.

### 3.2. Extractor de Spotify (`core/spotify_reader.py`)
Permite leer listas públicas sin credenciales de pago:
* **Lectura directa por URL (`extraer_canciones_por_url`)**:
  - Primero intenta el scraper de `spotdl` (`SpotifyClient`).
  - Fallback a HTTP nativo: Descarga el HTML de `open.spotify.com/playlist/<id>` y extrae el JSON embebido en la etiqueta `<script id="initialState">` (decodificando base64 si es necesario).
* **Búsqueda por Usuario (`buscar_playlists_usuario`)**:
  - Analiza perfiles públicos `open.spotify.com/user/<username>`.
  - **Nota técnica fundamental de Spotify**: Las páginas web de perfiles de Spotify solo renderizan las **10 primeras playlists públicas** en su HTML inicial (`publicPlaylistsV2`). Las listas adicionales se cargan mediante GraphQL interno protegido. Para solventar esto, la interfaz proporciona un acceso directo para abrir el perfil completo en Spotify y copiar el enlace directo de cualquier playlist.
* **Parseo de CSV (`parsear_csv_spotify`)**:
  - Lee y detecta dinámicamente columnas de canciones (`Track Name`, `Title`, `Artist`, etc.) para soportar exportaciones de herramientas como **Exportify**, **Spotlistr** o **Soundiiz**.

### 3.3. Motor de YouTube Music (`core/ytm_engine.py`)
Utiliza la librería `ytmusicapi` para gestionar la biblioteca de YouTube Music:
* **Autenticación y Priorización**:
  - `headers_auth.json` / `browser.json`: Basado en cabeceras HTTP capturadas del navegador (incluyendo la cookie `__Secure-3PAPISID` y el cálculo del hash `SAPISID`). **Es el método nativo más estable y compatible**.
  - `oauth.json`: Google Device Flow OAuth.
  - **Validación activa (`verificar_autenticacion_ytm`)**: Comprueba las credenciales ejecutando `yt.get_library_playlists(limit=1)`. Si la API InnerTube devuelve un Error 400 con OAuth (fallo conocido de Google con clientes OAuth de terceros en llamadas a bibliotecas), la función `encontrar_archivo_auth` conmuta automáticamente a `headers_auth.json`.
* **Búsqueda multietapa (`buscar_en_ytm`)**:
  - Etapa 1: Búsqueda exacta en catálogo oficial de canciones (`filter="songs"`).
  - Etapa 2: Búsqueda flexible eliminando signos de interrogación/admiración.
  - Etapa 3: Fallback a vídeos musicales oficiales (`filter="videos"`), asegurando encontrar canciones independientes o subidas como videoclips.
* **División por capacidad (`MAX_CANCIONES_LISTA_YTM = 5000`)**:
  - YouTube Music tiene un límite estricto de 5.000 canciones por playlist.
  - Si una lista supera este límite, el motor detecta el espacio libre y crea listas correlativas (`Nombre`, `Nombre 2`, `Nombre 3`...).
* **Simulación y Análisis Previo (`planificar_transferencia`)**:
  - Se ejecuta antes de tocar la cuenta de YouTube Music.
  - Compara la lista de Spotify contra las playlists existentes en YouTube Music.
  - Calcula:
    - Canciones que se añadirán a YouTube Music.
    - Canciones en común (ya presentes en YTM, para omitirlas y no duplicar).
    - **Canciones exclusivas de YouTube Music que no están en Spotify** (`solo_en_ytm`), generando para cada una de ellas el enlace de búsqueda directa en Spotify (`https://open.spotify.com/search/...`).

### 3.4. Gestor de Tareas Asíncronas (`core/job_runner.py`)
* Ejecuta transferencias en un hilo en segundo plano (`threading.Thread`).
* Almacena el progreso en memoria: porcentaje, canciones añadidas, canciones omitidas, no encontradas y eventos de log con marca de tiempo.
* Genera informes CSV descargables al finalizar:
  - `no_encontradas_<id>.csv`
  - `solo_en_spotify_<id>.csv`
  - `solo_en_ytm_<id>.csv`

---

## 4. Servidor Web y API REST (`web/app.py`)

### 4.1. Endpoints de la API
* `GET /api/status`: Devuelve el estado de autenticación de YouTube Music, el archivo de credenciales en uso y el total de playlists existentes.
* `POST /api/upload-auth`:
  - Acepta archivos JSON subidos o texto pegado.
  - **Soporte inteligente de cURL**: Si el usuario pega un comando copiado de las herramientas de desarrollador (`Copy as cURL`), el parser extrae las cabeceras tanto de los modificadores `-H` / `--header` como de las cookies en `-b` / `--cookie` (usadas por Google Chrome/Edge), convirtiéndolas automáticamente a `headers_auth.json` mediante `ytmusicapi.auth.browser.setup_browser`.
* `POST /api/oauth/init` y `GET /api/oauth/check/<session_id>`:
  - Gestiona el flujo OAuth Google Device Flow.
  - Persiste el estado de las sesiones en disco (`data/.oauth_flows.json`) para que no se pierdan entre peticiones distribuidas.
* `POST /api/fetch-url`: Extrae las canciones de una URL de Spotify.
* `POST /api/fetch-user`: Busca las playlists públicas de un usuario de Spotify y genera el enlace directo a su perfil web.
* `POST /api/upload-csv`: Procesa un archivo CSV de canciones.
* `POST /api/plan-transfer`: Devuelve la simulación previa con el desglose bidireccional de canciones.
* `POST /api/start-transfer`: Inicia la tarea de transferencia asíncrona.
* `GET /api/job-status/<job_id>`: Consulta en tiempo real el progreso de la transferencia.
* `GET /api/download-report/<job_id>/<tipo>`: Descarga informes CSV.

---

## 5. Decisiones Técnicas y Lecciones Aprendidas

1. **Gunicorn en Docker y Flask Threading**:
   - Gunicorn se debe configurar con `--workers 1 --threads 8`.
   - *Motivo*: Al manejar tareas en segundo plano (`threading`) y sesiones de sondeo en memoria/disco, el uso de múltiples procesos worker independientes (`--workers 3`) causaba que peticiones sucesivas cayeran en procesos distintos, perdiendo la referencia a la tarea o sesión activa. El modelo multihilo concurrente mantiene un único espacio de memoria compartido y maneja peticiones simultáneas de forma fluida.
2. **Healthcheck en Docker sin Dependencias de Sistema**:
   - En el `Dockerfile`, el healthcheck se ejecuta de forma nativa con Python:
     `CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/status')" || exit 1`
   - *Motivo*: Evita ejecutar `apt-get update && apt-get install curl` en el contenedor, lo que provocaba fallos de falta de memoria (`ResourceExhausted: cannot allocate memory`) en hosts con recursos limitados.
3. **Manejo de cookies en cURL desde Chrome DevTools**:
   - Al seleccionar *Copy as cURL (bash)* en Chrome o Edge, el navegador no usa `-H 'cookie: ...'`, sino el parámetro `-b '...'`. El backend analiza expresiones regulares para capturar tanto `-H` como `-b` y `--cookie`.
4. **Detección Bidireccional de Canciones**:
   - Añadir canciones a Spotify de forma automatizada requeriría un login OAuth completo de Spotify con alcance de modificación de playlists. La aplicación opta por una solución práctica: genera enlaces directos a la búsqueda de Spotify (`https://open.spotify.com/search/<cancion>`) que permiten añadir cualquier tema con un solo clic desde la interfaz.

---

## 6. Prompt Maestro para Recrear la Aplicación Completa

A continuación se incluye el prompt detallado que describe exhaustivamente el sistema para que un agente de IA pueda recrear todo el código de la solución:

```markdown
Eres un arquitecto de software y desarrollador experto en Python, Flask, Docker y APIs de streaming de música.
Tu objetivo es crear una suite completa para transferir y sincronizar playlists desde Spotify hacia YouTube Music (tanto en versión CLI como en aplicación Web moderna bajo Docker).

### Requisitos Principales:

1. **Independencia de Spotify Premium**:
   - El sistema debe extraer canciones de playlists públicas de Spotify sin requerir credenciales Premium ni cuentas de desarrollador obligatorias.
   - Utiliza una combinación de scraping resiliente (extrayendo el JSON `initialState` de las páginas públicas de Spotify) y la librería `spotdl` como respaldo.
   - Proporciona también soporte para importar archivos CSV generados por herramientas como Exportify o Soundiiz.

2. **Integración con YouTube Music**:
   - Utiliza la librería `ytmusicapi`.
   - Implementa soporte dual de autenticación:
     a) Extracción de cabeceras de navegador (`headers_auth.json`), aceptando tanto archivos JSON como comandos `curl` pegados directamente. El analizador de cURL debe extraer tanto argumentos `-H`/`--header` como `-b`/`--cookie` típicos de Google Chrome/Edge.
     b) Google Device OAuth (`oauth.json`), implementando un modal de verificación interactivo.
   - Implementa un verificador de autenticación activo que llame a `get_library_playlists(limit=1)` y priorice el método que realmente funcione sin error 400.

3. **Algoritmo de Normalización y Coincidencia Inteligente**:
   - Implementa un normalizador de títulos y artistas que elimine sufijos como "(Remastered)", "(Live)", "(Official Video)", "feat.", etc.
   - Aplica fuzzy matching con `difflib.SequenceMatcher` (umbral >= 0.82) y manejo de candidatos invertidos ("Artista - Título").
   - Búsqueda multietapa en YouTube Music: primero canciones oficiales (`songs`), luego variaciones sin signos de puntuación, y finalmente fallback a videoclips (`videos`).

4. **Sincronización Inteligente Bidireccional y Plan Previo**:
   - Antes de iniciar la transferencia, la interfaz debe ofrecer un "Análisis Previo / Plan de Sincronización":
     - Comprueba si la lista ya existe en YouTube Music.
     - Si existe, calcula cuántas canciones faltan por añadir y cuántas ya existen (para omitirlas y no duplicar).
     - Detecta si hay canciones en YouTube Music que NO están en Spotify (`solo_en_ytm`), mostrando enlaces directos de búsqueda en Spotify (`https://open.spotify.com/search/...`) para agregarlas con un clic, además de botones para copiar la lista o descargarla en `.txt`.
   - Si la playlist supera las 5.000 canciones (límite de YTM), debe dividirse automáticamente en listas correlativas ("Lista", "Lista 2", etc.).

5. **Aplicación Web y Docker (`web/`)**:
   - Backend en Flask con ejecución asíncrona de transferencias mediante hilos en segundo plano (`threading`).
   - Endpoint de sondeo de estado con reporte de logs en vivo con timestamp y barra de progreso porcentual.
   - UI responsiva con Bootstrap 5 en modo oscuro (estética Spotify/YouTube Music) y FontAwesome 6.
   - `Dockerfile` basado en `python:3.11-slim` con comprobación de salud (`HEALTHCHECK`) nativa mediante `urllib.request` (sin instalar `curl` ni ejecutar `apt-get`).
   - Servidor WSGI Gunicorn configurado en modo multihilo compartido (`--workers 1 --threads 8`) para evitar pérdidas de estado entre hilos.

6. **Script CLI Monolítico (`spotify_to_ytm.py`)**:
   - Script ejecutable de forma autónoma por consola con menús interactivos, soporte para los mismos tres orígenes (URL, Usuario, CSV), reporte en tiempo real en terminal y generación de informes CSV (`solo_en_spotify.csv`, `solo_en_youtube_music.csv`, `no_encontradas.csv`).
```

---

## 7. Instrucciones para Ejecutar y Probar el Proyecto

### Con Docker Compose (Recomendado):
```bash
cd web
docker compose up -d --build
```
La aplicación web estará disponible en: **`http://localhost:5000`**

### De forma local con Python:
```bash
cd web
pip install -r requirements.txt
python app.py
```

### Versión Terminal (CLI):
```bash
python spotify_to_ytm.py
```
