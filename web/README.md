# 🎵 Spotify to YouTube Music — Versión Web

Aplicación Web moderna y responsive para transferir y sincronizar playlists de **Spotify a YouTube Music**, optimizada para ejecutarse en servidores **Debian** mediante **Apache** y **Gunicorn**.

---

## ✨ Características Principales

- **3 Métodos de Entrada Sin Necesidad de Spotify Premium**:
  1. **Enlace Directo (URL)**: Pega cualquier URL pública de playlist de Spotify (soporta listas de más de 100 canciones).
  2. **Búsqueda por Usuario**: Introduce un nombre de usuario o enlace de perfil para descubrir y seleccionar sus playlists públicas interactivamente.
  3. **Subida de CSV**: Compatible con exportaciones de herramientas como Exportify, Soundiiz, Spotlistr, TuneMyMusic.
- **Sincronización Inteligente Bidireccional**: Comprueba si la lista ya existe en tu cuenta de YouTube Music y transfiere únicamente las canciones que faltan, evitando duplicados. Detecta canciones exclusivas de YouTube Music y genera accesos directos para agregarlas a Spotify.
- **Emparejamiento Difuso de Pistas**: Coincidencia inteligente multietapa entre títulos y artistas (`canciones_coinciden`), tolerando distinto orden de colaboradores, títulos bilingües con paréntesis y vídeos oficiales de YouTube subidos por canales uploader.
- **División Automática a 5.000 Canciones**: Respeta el límite máximo por lista de YouTube Music fragmentando listas grandes en "MiLista", "MiLista 2", etc.
- **Búsqueda Multietapa con Fallback a Vídeos Oficiales**: Si una canción indie no está catalogada como pista de audio en YouTube Music, el motor busca automáticamente su videoclip oficial correspondiente.
- **Monitor en Tiempo Real**: Barra de progreso animada, contadores de métricas en directo y consola de logs en vivo mientras se realiza la transferencia en segundo plano.
- **Informes de Exportación**: Descarga en CSV de canciones no encontradas y diferencias de catálogo.
- **Gestión Integrada de Credenciales de YouTube Music**: Subida y comprobación instantánea de `headers_auth.json` / `browser.json` directamente desde la interfaz web.

---

## 📁 Estructura del Proyecto

```
spotify-to-ytm-web/
├── Dockerfile                 # Contenedor Docker de producción con Gunicorn
├── docker-compose.yml         # Despliegue en 1 comando con volúmenes persistentes
├── .dockerignore              # Exclusión de temporales en la construcción
├── app.py                     # Servidor Flask y endpoints REST
├── wsgi.py                    # Punto de entrada WSGI para Gunicorn / mod_wsgi
├── requirements.txt           # Dependencias de Python
├── core/
│   ├── normalizer.py          # Coincidencia flexible de títulos y artistas
│   ├── spotify_reader.py      # Extracción por URL, perfil y CSV
│   ├── ytm_engine.py          # Interacción con la API de YouTube Music
│   └── job_runner.py          # Gestor de tareas asíncronas en segundo plano
├── templates/
│   └── index.html             # Interfaz web Single Page (Bootstrap 5)
├── static/
│   ├── css/style.css          # Estilos modernos temáticos de Spotify/YTM
│   └── js/app.js              # Lógica interactiva del frontend y polling
├── deploy/
│   ├── apache-spotify-ytm.conf# VirtualHost para Apache (Proxy Reverso)
│   ├── apache-wsgi.conf       # VirtualHost alternativo para mod_wsgi
│   ├── spotify-ytm.service    # Unidad systemd para Gunicorn
│   └── install_debian.sh      # Script de instalación desatendida para Debian
└── MANUAL_DEBIAN_APACHE.md    # Guía detallada de despliegue y administración
```

---

## 🐳 Despliegue con Docker y Docker Compose

Si prefieres aislar la aplicación en un contenedor Docker (en Debian, Ubuntu, Windows o cualquier servidor):

### Levantar el contenedor:
```bash
docker compose up -d --build
```

- La aplicación estará disponible en: `http://IP_DEL_SERVIDOR:5000`
- Incluye volúmenes persistentes para:
  - `./data`: credenciales de autenticación (`headers_auth.json`).
  - `./reports`: informes de canciones exportadas en CSV.
  - `./uploads`: archivos temporales.

### Detener el contenedor:
```bash
docker compose down
```

### Ver logs en vivo del contenedor:
```bash
docker compose logs -f
```

---

## 🚀 Despliegue Nativo en Debian con Apache

Para desplegar la aplicación directamente en Debian bajo Apache con nuestro script automatizado:

```bash
cd /ruta/spotify-to-ytm-web
chmod +x deploy/install_debian.sh
sudo ./deploy/install_debian.sh
```

Consulta el [MANUAL_DEBIAN_APACHE.md](MANUAL_DEBIAN_APACHE.md) para la configuración manual paso a paso, certificados SSL/HTTPS con Let's Encrypt y comandos de administración.

---

## 💻 Ejecución en Desarrollo Local (Windows / Linux)

Para probar la aplicación en tu máquina local antes de subirla a Debian:

1. Instala los requisitos:
   ```bash
   pip install -r requirements.txt
   ```
2. Ejecuta el servidor Flask:
   ```bash
   python app.py
   ```
3. Abre tu navegador en:
   ```
   http://localhost:5000
   ```
