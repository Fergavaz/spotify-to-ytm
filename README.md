# 🎶 Spotify → YouTube Music — Manual de Instalación y Uso

## Índice

1. [Requisitos previos](#1-requisitos-previos)
2. [Instalación](#2-instalación)
3. [Configuración de Spotify](#3-configuración-de-spotify)
4. [Configuración de YouTube Music](#4-configuración-de-youtube-music)
5. [Uso del script](#5-uso-del-script)
6. [Gestión de credenciales](#6-gestión-de-credenciales)
7. [Cuentas gratuitas y limitaciones](#7-cuentas-gratuitas-y-limitaciones)
8. [Funcionamiento detallado](#8-funcionamiento-detallado)
9. [Archivos generados](#9-archivos-generados)
10. [Solución de problemas](#10-solución-de-problemas)
11. [Preguntas frecuentes](#11-preguntas-frecuentes)

---

## 1. Requisitos previos

- **Python 3.10** o superior
- Una **cuenta de Spotify** (ver [sección 7](#7-cuentas-gratuitas-y-limitaciones) para detalles sobre cuentas gratuitas)
- Una **cuenta de Google** con YouTube Music
- Conexión a internet

### Comprobar la versión de Python

```bash
python --version
```

Si no tienes Python instalado, descárgalo desde [python.org](https://www.python.org/downloads/).

> **💡 Consejo:** Durante la instalación de Python en Windows, marca la casilla **"Add Python to PATH"**.

---

## 2. Instalación

### 2.1 Descargar el script

Descarga o copia el archivo `spotify_to_ytm.py` en una carpeta de tu elección, por ejemplo:

```
C:\Users\TU_USUARIO\Downloads\PYTHON\
```

### 2.2 Instalar dependencias

Abre una terminal (PowerShell o CMD) en la carpeta donde está el script y ejecuta:

```bash
pip install spotipy ytmusicapi cryptography spotifyscraper
```

Esto instalará las bibliotecas necesarias:

| Paquete           | Función                                                 |
|-------------------|---------------------------------------------------------|
| `spotifyscraper`  | Extrae playlists de Spotify directamente sin API/Premium|
| `spotipy`         | Acceso a la API oficial de Spotify (cuentas Premium)    |
| `ytmusicapi`      | Acceso a la API de YouTube Music                        |
| `cryptography`    | Cifrado AES de las credenciales almacenadas             |

---

## 3. Configuración de Spotify

Para acceder a tus playlists de Spotify necesitas crear una **aplicación** en el Portal de Desarrolladores de Spotify.

### 3.1 Crear una aplicación en Spotify

1. Ve a [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Inicia sesión con tu cuenta de Spotify.
3. Pulsa **"Create App"**.
4. Rellena los campos:
   - **App name:** `Spotify to YTM` (o el nombre que quieras)
   - **App description:** `Transferencia de playlists`
   - **Redirect URI:** `http://127.0.0.1:8888/callback`
   - **APIs used:** marca **Web API**
5. Acepta los términos y pulsa **"Save"**.

### 3.2 Obtener las credenciales

1. En tu aplicación, ve a **"Settings"**.
2. Copia el **Client ID**.
3. Pulsa **"View Client Secret"** y cópialo también.

### 3.3 Introducir las credenciales (automático)

**No necesitas configurar variables de entorno.** El script te pedirá las credenciales la primera vez que lo ejecutes:

```
🔑 Configuración de credenciales de Spotify
   Obtenlas en: https://developer.spotify.com/dashboard
   (Crea una app → Settings → Client ID / Client Secret)

   Client ID: ████████████████████████████████
   Client Secret: ████████████████████████████████
   🔒 Credenciales guardadas cifradas en: spotify_config.enc
```

Las credenciales se guardan **cifradas con AES-128 (Fernet)** en `spotify_config.enc`. En ejecuciones posteriores se usan automáticamente — ver [sección 6](#6-gestión-de-credenciales) para más detalles.

### 3.4 Primera autenticación OAuth

La primera vez que ejecutes el script, se abrirá el navegador para que autorices la aplicación de Spotify. Después de autorizar, se creará un archivo de caché (`.cache`) y no necesitarás volver a autorizarte.

---

## 4. Configuración de YouTube Music

### Opción A: OAuth (recomendada) ✅

Este método es más fiable y el token se renueva automáticamente.

1. Abre una terminal en la carpeta del script.
2. Ejecuta:

```bash
python -c "from ytmusicapi import YTMusic; YTMusic.setup_oauth(filepath='oauth.json')"
```

3. Se abrirá el navegador para que inicies sesión con tu cuenta de Google.
4. Autoriza la aplicación.
5. Se creará el archivo `oauth.json` en la misma carpeta.

### Opción B: Headers del navegador

Este método requiere copiar manualmente las cabeceras HTTP. El token expira con el tiempo.

1. Abre [YouTube Music](https://music.youtube.com) en tu navegador.
2. Inicia sesión con tu cuenta.
3. Abre las herramientas de desarrollador (F12) → pestaña **Red** (Network).
4. Recarga la página y busca cualquier petición a `music.youtube.com`.
5. Copia las cabeceras de la petición.
6. Ejecuta:

```bash
python -c "from ytmusicapi import YTMusic; YTMusic.setup(filepath='headers_auth.json')"
```

7. Pega las cabeceras cuando se te solicite.

> **💡 Consejo:** El script busca automáticamente `oauth.json` primero, y si no existe, usa `headers_auth.json`. También puedes especificar la ruta con la variable de entorno `YTM_AUTH_FILE`.

---

## 5. Uso del script

### 5.1 Ejecución

Abre una terminal en la carpeta del script y ejecuta:

```bash
python spotify_to_ytm.py
```

### 5.2 Flujo interactivo

El script te guiará paso a paso:

```
======================================================================
  🎶  SPOTIFY → YOUTUBE MUSIC — Transferencia de Playlists  🎶
======================================================================

🔗 Conectando con Spotify...
   Usando credenciales guardadas...
   Conectado como: Tu Nombre (premium)
   ⚠  Recuerda: solo se pueden leer playlists propias o colaborativas.

🔗 Conectando con YouTube Music...
   Conexión establecida.

🎵 Obteniendo tus playlists de Spotify...

   #  Playlist                                           Canciones  Propietario
─────────────────────────────────────────────────────────────────────────────────
   1  Española                                                 850  Tu Nombre
   2  Rock Clásico                                             200  Tu Nombre
   3  Chill Vibes                                              150  Tu Nombre

Selecciona el número de la playlist a transferir (0 para cancelar): 1

✅ Seleccionada: "Española" (850 canciones)

🔍 Buscando listas "Española" en YouTube Music...
   Encontradas: Española
   Total de canciones en YTM: 800

📋 Resultado de la comparación:
   ▸ Canciones en común: ~800
   ▸ Solo en Spotify (faltan en YTM): 50
   ▸ Solo en YTM (no están en Spotify): 5

🔄 Se van a buscar 50 canciones en YouTube Music.
   ¿Deseas continuar? (s/N): s

🔎 Buscando 50 canciones en YouTube Music...
   [1/50] ✅ La Flaca — Jarabe de Palo
   [2/50] ✅ Entre dos aguas — Paco de Lucía
   ...

📥 Añadiendo 48 canciones a YouTube Music...
  ➕ Añadiendo 48 canciones a "Española"...
  ✅ Añadidas 48 canciones a "Española"

======================================================================
  🎉  ¡Transferencia completada!  🎉
======================================================================
```

### 5.3 Listas con más de 5000 canciones

YouTube Music tiene un **límite de 5000 canciones por lista**. Si tu playlist excede este límite, el script automáticamente:

1. Llena la lista existente hasta 5000.
2. Crea listas adicionales con nombre numerado:
   - `Española` (5000 canciones)
   - `Española 2` (5000 canciones)
   - `Española 3` (canciones restantes)

Después puedes combinar manualmente las listas en YouTube Music.

---

## 6. Gestión de credenciales

### 6.1 Almacenamiento seguro

Las credenciales de Spotify (**Client ID** y **Client Secret**) se almacenan cifradas en el archivo `spotify_config.enc` usando:

| Aspecto            | Detalle                                                  |
|--------------------|----------------------------------------------------------|
| **Algoritmo**      | AES-128-CBC (Fernet)                                    |
| **Clave derivada** | PBKDF2-HMAC-SHA256 con 150.000 iteraciones              |
| **Semilla**        | Nombre de usuario + nombre de máquina (automático)       |
| **Resultado**      | El archivo solo puede descifrarse en tu usuario/máquina  |

### 6.2 Flujo de credenciales

El script sigue esta prioridad para obtener las credenciales:

```
1. ¿Existe spotify_config.enc con credenciales válidas? → Usar esas
   ↓ No
2. ¿Existen variables de entorno SPOTIPY_CLIENT_ID/SECRET? → Usar y guardar
   ↓ No
3. Solicitar al usuario interactivamente → Validar y guardar
```

### 6.3 Renovación automática

Si las credenciales guardadas dejan de funcionar (por ejemplo, si las revocas en el Spotify Developer Dashboard), el script:

1. Detecta el error automáticamente.
2. Elimina la caché de tokens (`.cache`).
3. Te solicita las nuevas credenciales.
4. Las guarda cifradas para futuras ejecuciones.

### 6.4 Restablecer credenciales manualmente

Si quieres introducir credenciales nuevas, simplemente elimina el archivo:

```bash
del spotify_config.enc
```

La próxima vez que ejecutes el script, te las pedirá de nuevo.

---

## 7. Cuentas gratuitas y limitaciones

### 7.1 ¿Por qué la API oficial falla en cuentas Free?

El mensaje de error que devuelve Spotify:
```text
HTTP Error for GET to https://api.spotify.com/v1/me/ returned 403 due to Active premium subscription required for the owner of the app.
```

**Significa:**
- Tus credenciales (Client ID y Client Secret) **son completamente válidas**.
- Sin embargo, **Spotify ha bloqueado el acceso a su Web API** a todas las aplicaciones creadas por usuarios sin suscripción activa a **Spotify Premium**.

### 7.2 ¿Cómo lo resuelve el script? (Extracción directa como Exportify)

¡No necesitas salir a ninguna web externa ni tener Spotify Premium! El script ahora integra tres métodos sencillos:

**Opción 1: Pegar el enlace directo de Spotify (URL)**
1. En Spotify (app de PC, móvil o web), haz clic derecho en la playlist que quieras transferir → **Compartir** → **Copiar enlace a la playlist**.
2. Al ejecutar el script, elige la opción `1` y pega el enlace (ej: `https://open.spotify.com/playlist/...`).
3. El script extraerá automáticamente el nombre de la playlist y todas las pistas con sus artistas.

**Opción 2: Buscar por nombre de usuario de Spotify**
1. Elige la opción `2` en el script.
2. Escribe el nombre de usuario de Spotify (o pega el enlace a su perfil, ej: `https://open.spotify.com/user/nombre`).
3. El script buscará sus playlists públicas y te mostrará una lista numerada con el nombre y número de canciones de cada una.
4. Solo tienes que teclear el número de la lista que quieras transferir.

**Opción 3: Usar un archivo CSV existente**
Si ya dispones de un archivo `.csv` descargado con Exportify, Soundiiz o TuneMyMusic, puedes colocarlo en la misma carpeta del script y elegir la opción `3`.

### 7.3 Playlists de cualquier usuario sin restricciones
Con los métodos directos (Opción 1 y Opción 2), puedes transferir **cualquier lista pública de cualquier usuario**, sin importar si la lista es tuya o de un amigo.

---

## 8. Funcionamiento detallado

### 8.1 Algoritmo de comparación

El script no compara los títulos literalmente, sino que utiliza un algoritmo inteligente:

1. **Normaliza** los textos: elimina acentos, paréntesis, indicaciones como "feat.", "Remastered", "Video Oficial", etc.
2. **Compara** usando similitud de secuencias (umbral del 88%).
3. Verifica tanto el **título** como el **artista principal**.

Esto permite detectar que, por ejemplo, `"La Flaca (Remastered)"` y `"La Flaca"` son la misma canción.

### 8.2 Flujo de transferencia

```
┌─────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Spotify    │───▶│   Comparación    │───▶│  YouTube Music   │
│  (playlist)  │    │   inteligente    │    │  (añadir/crear)  │
└─────────────┘    └──────────────────┘    └─────────────────┘
       │                    │                       │
       ▼                    ▼                       ▼
  Lista completa    Canciones que         Canciones añadidas
  de canciones      faltan en YTM         a lista(s) YTM
```

---

## 9. Archivos generados

| Archivo                      | Descripción                                                  |
|------------------------------|--------------------------------------------------------------|
| `spotify_config.enc`         | **Credenciales de Spotify cifradas** (AES-128/Fernet)        |
| `.cache`                     | Token OAuth de Spotify (no eliminar)                         |
| `oauth.json`                 | Credenciales de YouTube Music — OAuth                        |
| `solo_en_spotify.csv`        | Canciones que están en Spotify pero no en YouTube Music       |
| `solo_en_youtube_music.csv`  | Canciones que están en YTM pero no en Spotify                 |
| `no_encontradas_en_ytm.csv`  | Canciones de Spotify que no se pudieron encontrar en YTM      |

> **⚠ Seguridad:** Los archivos `spotify_config.enc`, `.cache`, `oauth.json` y `headers_auth.json` contienen tokens o credenciales. **No los compartas** ni los subas a repositorios públicos. Añade estos archivos a tu `.gitignore`.

---

## 10. Solución de problemas

### ❌ "ModuleNotFoundError: No module named 'cryptography'"

**Causa:** La dependencia `cryptography` no está instalada.

**Solución:**

```bash
pip install cryptography
```

---

### ❌ Las credenciales guardadas no funcionan después de cambiar de usuario/máquina

**Causa:** Las credenciales están cifradas con una clave derivada del nombre de usuario y la máquina. Si cambias de usuario o máquina, no se pueden descifrar.

**Solución:** El script lo detecta automáticamente y te pide las credenciales de nuevo. Si quieres forzarlo:

```bash
del spotify_config.enc
```

---

### ❌ "No se obtuvieron canciones de esta playlist"

**Causa:** La playlist no te pertenece y no colaboras en ella. Desde 2024, la API de Spotify no permite leer canciones de playlists ajenas.

**Solución:** Copia la playlist a tu biblioteca desde la app de Spotify (botón ⋯ → "Copiar a tu biblioteca") y selecciónala de nuevo.

---

### ❌ "No se encuentra el archivo de autenticación..."

**Causa:** No se ha generado el archivo `oauth.json` o `headers_auth.json`.

**Solución:** Sigue los pasos de la [sección 4](#4-configuración-de-youtube-music).

---

### ❌ La autenticación de Spotify abre el navegador pero no redirige

**Causa:** El Redirect URI no coincide.

**Solución:** Asegúrate de que en el Dashboard de Spotify el Redirect URI sea exactamente:

```
http://127.0.0.1:8888/callback
```

---

### ❌ Algunas canciones no se encuentran en YouTube Music

**Causa normal:** No todas las canciones de Spotify están disponibles en YouTube Music.

**Solución:** Revisa el archivo `no_encontradas_en_ytm.csv` y búscalas manualmente.

---

### ❌ "HTTP Error 429" o la búsqueda se bloquea

**Causa:** Demasiadas peticiones a la API de YouTube Music.

**Solución:** El script ya incluye pausas entre búsquedas y envía canciones en lotes de 50. Si sigues teniendo problemas, edita `PAUSA_BUSQUEDA` en el script y auméntalo (p. ej., `0.5` o `1.0`).

---

### ❌ El token de YouTube Music ha expirado

**Causa:** Si usas `headers_auth.json`, el token expira periódicamente.

**Solución:** Regenera el archivo con `YTMusic.setup()` o migra al método OAuth (recomendado).

---

## 11. Preguntas frecuentes

### ¿Puedo transferir playlists de las que no soy propietario?

**No directamente.** Desde 2024, la API de Spotify no devuelve las canciones de playlists ajenas. Solución: copia primero la playlist a tu biblioteca desde la app de Spotify.

### ¿El script duplica canciones?

**No.** El script compara las canciones existentes y solo añade las que faltan.

### ¿Puedo ejecutar el script varias veces para la misma playlist?

**Sí.** Cada vez que lo ejecutes, solo se añadirán las canciones nuevas que no estén ya en YouTube Music.

### ¿Mis credenciales están seguras?

Las credenciales se almacenan cifradas con AES-128 (Fernet). La clave de cifrado se deriva de tu nombre de usuario y tu máquina, por lo que el archivo `spotify_config.enc` no puede descifrarse en otro equipo ni por otro usuario. Sin embargo, no es un sistema infalible — no compartas el archivo.

### ¿Funciona con playlists colaborativas?

**Sí**, tanto las de Spotify como las de YouTube Music.

### ¿Se transfiere el orden de las canciones?

Las canciones se añaden en el orden en que aparecen en la playlist de Spotify. Se añaden al final de la lista de YouTube Music existente.

### ¿Cómo combino las listas numeradas en YouTube Music?

Desde la app de YouTube Music, abre la lista destino, añade canciones buscando en tus otras listas, o mantén las listas separadas.

### ¿El script funciona en Linux/macOS?

**Sí.** El script es multiplataforma. El cifrado de credenciales funciona de la misma manera en todos los sistemas operativos.

---

## Estructura de archivos

```
📁 TU_CARPETA/
├── 📄 spotify_to_ytm.py          ← Script principal
├── 🔒 spotify_config.enc         ← Credenciales Spotify cifradas (se genera)
├── 📄 oauth.json                  ← Credenciales YTM (se genera)
├── 📄 .cache                      ← Token Spotify (se genera)
├── 📄 solo_en_spotify.csv         ← Informe (se genera)
├── 📄 solo_en_youtube_music.csv   ← Informe (se genera)
└── 📄 no_encontradas_en_ytm.csv   ← Informe (se genera)
```

---

## Inicio rápido (TL;DR)

```bash
# 1. Instalar dependencias
pip install spotipy ytmusicapi cryptography

# 2. Configurar YouTube Music (una vez)
python -c "from ytmusicapi import YTMusic; YTMusic.setup_oauth(filepath='oauth.json')"

# 3. Ejecutar — las credenciales de Spotify se piden automáticamente
python spotify_to_ytm.py
```

---

**Autor:** Generado con ❤ y AI
**Licencia:** Uso libre
