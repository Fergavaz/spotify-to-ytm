# 📖 Manual de Despliegue en Debian Linux con Apache
## Spotify to YouTube Music — Versión Web

Este documento detalla cómo desplegar y servir la aplicación web de transferencia de listas de Spotify a YouTube Music en un servidor **Debian GNU/Linux** utilizando **Apache2** como servidor web y **Gunicorn** como servidor de aplicaciones Python gestionado por **systemd**.

---

## 🏛️ Arquitectura del Sistema

```
  [ Navegador del Usuario ]
             │
             │ HTTP / HTTPS (Puertos 80 / 443)
             ▼
  ┌───────────────────────────────────────────────┐
  │                 Servidor Debian               │
  │                                               │
  │  ┌─────────────────────────────────────────┐  │
  │  │         Servidor Web Apache 2           │  │
  │  │   (Proxy Reverso + SSL + Archivos CSS)  │  │
  │  └────────────────────┬────────────────────┘  │
  │                       │ Proxy inverso         │
  │                       ▼ (127.0.0.1:5000)      │
  │  ┌─────────────────────────────────────────┐  │
  │  │                Gunicorn                 │  │
  │  │        (Servicio systemd en venv)       │  │
  │  └────────────────────┬────────────────────┘  │
  │                       │                       │
  │  ┌────────────────────▼────────────────────┐  │
  │  │       Aplicación Flask (app.py)         │  │
  │  │   - Búsqueda en Spotify (Scraper / CSV) │  │
  │  │   - Interacción con YouTube Music API   │  │
  │  │   - Tareas asíncronas en segundo plano  │  │
  │  └─────────────────────────────────────────┘  │
  └───────────────────────────────────────────────┘
```

Esta arquitectura es el estándar en entornos de producción:
- **Apache** gestiona las conexiones externas, el cortafuegos, el cifrado SSL/TLS y el contenido estático.
- **Gunicorn** ejecuta la aplicación Flask en un entorno virtual aislado (`venv`).
- **systemd** garantiza que la aplicación arranque automáticamente al reiniciar el servidor y se reinicie en caso de fallo.

---

## 🚀 Método 1: Instalación Automática (Recomendada)

Si ya has copiado la carpeta `spotify-to-ytm-web` a tu servidor Debian:

1. Accede por SSH a tu servidor Debian.
2. Entra en la carpeta de la aplicación:
   ```bash
   cd /ruta/hacia/spotify-to-ytm-web
   ```
3. Otorga permisos de ejecución al instalador y ejecútalo como root:
   ```bash
   chmod +x deploy/install_debian.sh
   sudo ./deploy/install_debian.sh
   ```

El script se encargará automáticamente de:
- Instalar `apache2`, `python3-venv`, `python3-pip`.
- Habilitar los módulos de Apache `proxy`, `proxy_http` y `headers`.
- Copiar la app a `/var/www/spotify-to-ytm-web`.
- Crear el entorno virtual `venv` e instalar todas las librerías.
- Configurar y arrancar el servicio de sistema `spotify-ytm.service`.
- Activar el sitio en Apache y reiniciar el servicio.

Una vez terminado, abre tu navegador y entra en la IP de tu servidor:
`http://IP_DE_TU_SERVIDOR/`

---

## 🛠️ Método 2: Instalación Manual Paso a Paso

Si prefieres realizar cada paso manualmente:

### Paso 1: Instalar paquetes del sistema
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip apache2
```

### Paso 2: Habilitar módulos necesarios en Apache
```bash
sudo a2enmod proxy proxy_http headers rewrite
sudo systemctl restart apache2
```

### Paso 3: Ubicar los archivos de la aplicación
Copia la carpeta del proyecto a `/var/www/spotify-to-ytm-web`:
```bash
sudo mkdir -p /var/www/spotify-to-ytm-web
sudo cp -r ./* /var/www/spotify-to-ytm-web/
```

### Paso 4: Crear el Entorno Virtual de Python e instalar dependencias
```bash
cd /var/www/spotify-to-ytm-web
sudo python3 -m venv venv
sudo ./venv/bin/pip install --upgrade pip
sudo ./venv/bin/pip install -r requirements.txt
```

### Paso 5: Configurar permisos
Asegura que el usuario `www-data` pueda escribir en los directorios de subida y reportes:
```bash
sudo chown -R www-data:www-data /var/www/spotify-to-ytm-web
sudo chmod -R 775 /var/www/spotify-to-ytm-web/uploads
sudo chmod -R 775 /var/www/spotify-to-ytm-web/reports
```

### Paso 6: Crear el Servicio systemd
Crea el archivo `/etc/systemd/system/spotify-ytm.service`:
```bash
sudo nano /etc/systemd/system/spotify-ytm.service
```

Pega el siguiente contenido:
```ini
[Unit]
Description=Spotify to YouTube Music Web Service (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/spotify-to-ytm-web
Environment="PATH=/var/www/spotify-to-ytm-web/venv/bin"
ExecStart=/var/www/spotify-to-ytm-web/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Inicia y habilita el servicio:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-ytm
```

Comprueba que esté activo:
```bash
sudo systemctl status spotify-ytm
```

### Paso 7: Configurar VirtualHost en Apache
Crea el archivo `/etc/apache2/sites-available/spotify-ytm.conf`:
```bash
sudo nano /etc/apache2/sites-available/spotify-ytm.conf
```

Contenido del VirtualHost:
```apache
<VirtualHost *:80>
    ServerName spotify-ytm.local
    ServerAdmin webmaster@localhost

    # Servir archivos estáticos directamente mediante Apache
    Alias /static /var/www/spotify-to-ytm-web/static
    <Directory /var/www/spotify-to-ytm-web/static>
        Require all granted
    </Directory>

    # Proxy inverso hacia Gunicorn
    ProxyPreserveHost On
    ProxyPass /static !
    ProxyPass / http://127.0.0.1:5000/
    ProxyPassReverse / http://127.0.0.1:5000/

    RequestHeader set X-Forwarded-Proto "http"
    RequestHeader set X-Forwarded-Port "80"

    ErrorLog ${APACHE_LOG_DIR}/spotify_ytm_error.log
    CustomLog ${APACHE_LOG_DIR}/spotify_ytm_access.log combined
</VirtualHost>
```

Habilita el sitio y recarga Apache:
```bash
sudo a2ensite spotify-ytm.conf
sudo systemctl reload apache2
```

---

## 🐳 Método 3: Despliegue con Docker (Detrás de Apache)

Si prefieres aislar completamente la aplicación en un contenedor Docker en Debian y dejar que Apache maneje el dominio y SSL:

1. Instala Docker y Docker Compose en Debian (si no lo tienes):
   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose-v2
   sudo systemctl enable --now docker
   ```

2. Entra en el directorio de la aplicación y levanta el contenedor:
   ```bash
   cd /ruta/spotify-to-ytm-web
   docker compose up -d --build
   ```

3. El contenedor expondrá internamente el puerto `5000`. Configura Apache para hacer de proxy inverso hacia él usando el archivo [apache-spotify-ytm.conf](deploy/apache-spotify-ytm.conf):
   ```bash
   sudo cp deploy/apache-spotify-ytm.conf /etc/apache2/sites-available/spotify-ytm.conf
   sudo a2ensite spotify-ytm.conf
   sudo systemctl reload apache2
   ```

4. Para ver el estado o los logs del contenedor Docker:
   ```bash
   docker compose ps
   docker compose logs -f
   ```

---

## 🔐 Configuración de Autenticación de YouTube Music

Para que el servidor web o el contenedor Docker puedan gestionar tus listas de YouTube Music, dispones de dos métodos:

### Método 1: Google OAuth (Recomendado y Permanente)
1. En la web, pulsa en **Configurar YTM** → pestaña **Google OAuth**.
2. Escribe tu Client ID y Client Secret de Google Cloud.
3. Pulsa **Conectar con Google** y autoriza tu cuenta. El token se renovará automáticamente y nunca caducará.

---

### Método 2: Cabeceras del Navegador (`headers_auth.json` / `browser.json`)
Si no deseas crear credenciales de desarrollador en Google Cloud, puedes extraer las cabeceras de sesión de tu navegador en 1 minuto.

#### 📋 Paso a paso para Google Chrome, Microsoft Edge y Brave:
1. Abre tu navegador e inicia sesión en [music.youtube.com](https://music.youtube.com).
2. Pulsa la tecla <kbd>F12</kbd> (o clic derecho en cualquier parte → *Inspeccionar*) para abrir las Herramientas de Desarrollador.
3. Ve a la pestaña **Red** (o *Network* en inglés).
4. En el campo de filtro o búsqueda escribe: `browse`.
5. En la página de YouTube Music, haz clic en **"Biblioteca"** o en **"Explorar"** en el menú de la izquierda.
6. Verás aparecer en la lista de red una petición llamada `browse` (con estado 200).
7. Haz clic derecho sobre esa petición `browse`:
   - En **Chrome / Brave**: Selecciona **Copiar** → **Copiar como cURL** (o *Copiar cabeceras de solicitud*).
   - En **Edge**: Selecciona **Copiar** → **Copiar como cURL** (o *Copiar cabeceras de solicitud*).
8. Vuelve a la aplicación web, abre el modal **Configurar YTM**, ve a la pestaña **Pegar Cabeceras o cURL**, pega el contenido y pulsa **Convertir, Guardar y Validar**. El conversor detectará automáticamente el formato y creará un archivo válido.

#### 🦊 Paso a paso para Mozilla Firefox:
1. Abre Firefox e inicia sesión en [music.youtube.com](https://music.youtube.com).
2. Pulsa <kbd>F12</kbd> y selecciona la pestaña **Red** (*Network*).
3. Escribe `browse` en el filtro.
4. Pulsa en **Biblioteca** dentro de YouTube Music.
5. Clic derecho en la petición `browse` → **Copiar** → **Copiar como cURL**.
6. Pégalo en la pestaña **Pegar Cabeceras o cURL** de la web.

#### 💻 Generación mediante terminal (Alternativa):
Si prefieres generar el archivo con Python en tu terminal:
```bash
python -c "from ytmusicapi import YTMusic; YTMusic.setup(filepath='headers_auth.json')"
```
Sigue las indicaciones de pantalla y pega las cabeceras copiadas. Luego copia el archivo `headers_auth.json` a la carpeta `data/` de la aplicación o del contenedor Docker.

---

## 🔒 Configurar HTTPS / SSL con Let's Encrypt (Certbot)

Si tienes un dominio apuntando a tu servidor Debian (ej. `musica.tudominio.com`), puedes activar HTTPS gratuito en 1 minuto:

```bash
sudo apt install -y certbot python3-certbot-apache
sudo certbot --apache -d musica.tudominio.com
```

Certbot actualizará automáticamente la configuración de Apache para redireccionar todo el tráfico a HTTPS de forma segura.

---

## 📋 Comandos de Mantenimiento y Diagnóstico

| Acción | Comando |
|---|---|
| **Ver estado del servicio web** | `sudo systemctl status spotify-ytm` |
| **Reiniciar la aplicación web** | `sudo systemctl restart spotify-ytm` |
| **Ver logs en tiempo real** | `sudo journalctl -u spotify-ytm -f` |
| **Ver errores de Apache** | `sudo tail -f /var/log/apache2/spotify_ytm_error.log` |
| **Reiniciar Apache** | `sudo systemctl reload apache2` |
