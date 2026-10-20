# 🎶 Spotify to YouTube Music (CLI & Web)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Herramienta completa para transferir y sincronizar playlists de **Spotify a YouTube Music**.

Disponible en dos modalidades independientes:
1. 💻 **Modo Script de Consola (CLI)**: Para ejecutar interactivamente desde tu terminal en Windows, Linux o macOS.
2. 🌐 **Modo Aplicación Web & Docker**: Para servir una interfaz visual moderna mediante **Docker**, o en **Apache sobre Debian Linux**.

---

## 🌟 Características Destacadas

- **Sin necesidad de Spotify Premium**:
  - Pega el enlace directo de cualquier playlist pública de Spotify (incluso con más de 100 canciones).
  - O busca por nombre de usuario de Spotify y explora interactivamente sus listas públicas.
  - O sube un archivo CSV (compatible con Exportify, Soundiiz, Spotlistr, TuneMyMusic).
  - Soporte opcional para la API oficial de desarrolladores de Spotify.
- **Sincronización Inteligente**: Compara las canciones de tu lista de Spotify con las ya existentes en YouTube Music y añade únicamente las que faltan, evitando duplicados.
- **División Automática a 5.000 Canciones**: Respeta el límite máximo por lista de YouTube Music fragmentando playlists grandes en listas numeradas: `"MiLista"`, `"MiLista 2"`, etc.
- **Búsqueda Multietapa con Fallback a Vídeos Oficiales**: Si una pista indie no aparece en el catálogo de audio (`songs`), busca automáticamente su videoclip oficial correspondiente (`videos`).
- **Informes CSV de Diferencias**: Genera listados detallados con las canciones transferidas, no encontradas o exclusivas de cada plataforma.

---

## 📁 Estructura del Repositorio

```
spotify-to-ytm/
├── spotify_to_ytm.py          # Script interactivo de consola (Modo CLI)
├── README.md                  # Este documento
├── .gitignore                 # Filtro de seguridad (credenciales y temporales)
└── web/                       # Versión Web completa (Modo Web)
    ├── Dockerfile             # Imagen Docker de producción con Gunicorn
    ├── docker-compose.yml     # Orquestación con volúmenes persistentes
    ├── app.py                 # Servidor Flask y API REST
    ├── wsgi.py                # Entrada WSGI para Gunicorn / mod_wsgi
    ├── requirements.txt       # Dependencias web
    ├── core/                  # Motores de scraping, normalización y YTM
    ├── templates/index.html   # Interfaz gráfica Single Page
    ├── static/                # Estilos CSS oscuros y lógica JS
    ├── deploy/                # Instalador y VirtualHosts de Apache para Debian
    └── MANUAL_DEBIAN_APACHE.md# Guía paso a paso para Debian y Apache
```

---

## 🌐 OPCIÓN A: Modo Aplicación Web & Docker

### 🐳 1. Ejecutar con Docker (Cualquier sistema operativo)

Si tienes Docker y Docker Compose instalados:

```bash
cd web
docker compose up -d --build
```

- La aplicación estará disponible de inmediato en: **`http://localhost:5000`** (o `http://IP_DE_TU_SERVIDOR:5000`).
- Configuración persistente en `./data` (guarda tus credenciales de YouTube Music).
- Informes descargables en `./reports`.

Para ver los logs en directo:
```bash
docker compose logs -f
```

---

### 🐧 2. Despliegue en Debian con Apache

Para servir la aplicación en un servidor Debian mediante **Apache2** (Proxy Reverso) y **Gunicorn** como servicio de sistema `systemd`:

1. Copia la carpeta `web/` a tu servidor Debian.
2. Ejecuta el instalador automatizado incluido:
   ```bash
   cd web
   chmod +x deploy/install_debian.sh
   sudo ./deploy/install_debian.sh
   ```
El script instalará las dependencias del sistema, creará el entorno virtual `venv`, habilitará los módulos de Apache y dejará la aplicación corriendo en segundo plano.

> 📖 Para ver el manual completo de administración de Apache, cortafuegos y certificados SSL gratuitos con Let's Encrypt (Certbot), consulta el [MANUAL_DEBIAN_APACHE.md](web/MANUAL_DEBIAN_APACHE.md).

---

## 💻 OPCIÓN B: Modo Script de Consola (CLI)

### 1. Requisitos Previos

- **Python 3.10** o superior.
- Una cuenta de Google con YouTube Music.
- Conexión a internet.

### 2. Instalación de Dependencias

```bash
pip install spotipy ytmusicapi cryptography spotifyscraper
```

| Paquete | Función |
|---|---|
| `spotifyscraper` | Extrae playlists de Spotify sin cuenta Premium ni API keys |
| `spotipy` | Conexión con la API oficial de Spotify (opcional) |
| `ytmusicapi` | Conexión y gestión de listas en YouTube Music |
| `cryptography` | Cifrado determinista AES-128 de credenciales locales |

---

### 3. Configuración de YouTube Music

YouTube Music requiere un archivo de sesión (`oauth.json` o `headers_auth.json`).

#### Método 1: OAuth (Recomendado)
Ejecuta en tu terminal:
```bash
python -c "from ytmusicapi import YTMusic; YTMusic.setup_oauth(filepath='oauth.json')"
```
Sigue las instrucciones en pantalla para iniciar sesión con Google y autorizar la aplicación.

#### Método 2: Headers del Navegador
1. Inicia sesión en [music.youtube.com](https://music.youtube.com).
2. Abre la consola de desarrollo del navegador (`F12`) y ve a la pestaña **Red (Network)**.
3. Filtra por `browse` y copia las cabeceras de la petición como cURL.
4. Ejecuta:
   ```bash
   python -c "from ytmusicapi import YTMusic; YTMusic.setup(filepath='headers_auth.json')"
   ```
   y pega las cabeceras solicitadas.

---

### 4. Configuración Opcional de Spotify API

Si dispones de cuenta de desarrollador de Spotify:
1. Crea una aplicación en [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Añade como Redirect URI: `http://127.0.0.1:8888/callback`.
3. El script te solicitará el **Client ID** y **Client Secret** la primera vez y los guardará cifrados con AES en `spotify_config.enc`.

*Si tu cuenta de Spotify es Free (sin Premium), no te preocupes: el script cambiará automáticamente al modo de extracción directa sin limitaciones.*

---

### 5. Ejecución del Script

```bash
python spotify_to_ytm.py
```

El script te ofrecerá un menú interactivo:
```
  🎵 MODO SIN SPOTIFY PREMIUM (Extracción directa)
──────────────────────────────────────────────────────────────────────
  Opciones disponibles para transferir:
    1) Pegar el enlace/URL de la playlist
    2) Buscar por nombre de usuario de Spotify y elegir entre sus listas
    3) Usar un archivo CSV existente (Exportify / Soundiiz)
──────────────────────────────────────────────────────────────────────
```

1. Selecciona la opción deseada.
2. El script comprobará si la lista ya existe en YouTube Music y mostrará las canciones que faltan.
3. Confirmas y el motor añadirá las pistas en lotes de forma segura.

---

## 🧠 Algoritmo de Normalización y Búsqueda

El sistema no realiza búsquedas literales rígidas, sino que implementa una canalización en varias etapas:

1. **Limpieza y Normalización**:
   - Elimina acentos, puntuaciones irrelevantes y cadenas accesorias (`feat.`, `Remastered`, `Live`, `Bonus Track`, `Deluxe Edition`).
   - Normaliza variantes ortográficas (`¿ ? ¡ !`).
2. **Búsqueda en Catálogo de Pistas (`songs`)**:
   - Comprueba la coincidencia difusa entre el título y el artista con un umbral del 88% de similitud.
3. **Fallback a Videoclips Oficiales (`videos`)**:
   - Muchas canciones independientes o ediciones especiales están catalogadas en YouTube Music como videoclips oficiales. Si la búsqueda en `songs` no arroja resultado, el motor realiza automáticamente una segunda pasada en `videos`.

---

## 📄 Archivos Generados e Informes

| Archivo | Descripción |
|---|---|
| `spotify_config.enc` | Credenciales de desarrollador de Spotify cifradas con AES-128 |
| `oauth.json` / `headers_auth.json` | Credenciales de sesión de YouTube Music |
| `solo_en_spotify.csv` | Pistas presentes en Spotify que no estaban en YTM |
| `solo_en_youtube_music.csv` | Pistas que ya existían en YTM pero no estaban en Spotify |
| `no_encontradas_en_ytm.csv` | Pistas de Spotify que no pudieron localizarse en YouTube Music |

> ⚠️ **Seguridad:** Los archivos `.json`, `.enc` y `.cache` contienen información sensible de tus sesiones. Están incluidos en el `.gitignore` para prevenir subidas accidentales a repositorios públicos.

---

## 🤝 Contribuciones y Soporte

Las contribuciones, sugerencias y mejoras son bienvenidas. Puedes abrir un *Issue* o enviar un *Pull Request*.
