# 🚀 Guía de Instalación Rápida en Debian con Apache

Este paquete contiene todo el código y configuración necesarios para servir **Spotify to YouTube Music** como una aplicación web nativa en **Debian GNU/Linux** con **Apache2** y **Gunicorn** (sin Docker).

---

## ⚡ Opción 1: Instalación Automática en 1 Paso (Recomendada)

1. Sube y descomprime el archivo `.zip` en tu servidor Debian (por ejemplo en tu carpeta de usuario `/home/tu_usuario/` o en `/tmp/`):
   ```bash
   unzip spotify-to-ytm-debian.zip -d spotify-to-ytm-web
   cd spotify-to-ytm-web
   ```

2. Dale permisos de ejecución al script de instalación y ejecútalo como root:
   ```bash
   chmod +x deploy/install_debian.sh
   sudo ./deploy/install_debian.sh
   ```

El script se encargará automáticamente de:
- Instalar Apache2, Python 3, venv y módulos de proxy inverso (`proxy`, `proxy_http`, `headers`).
- Copiar la aplicación a `/var/www/spotify-to-ytm-web/`.
- Crear el entorno virtual `venv` e instalar todas las dependencias (`requirements.txt`).
- Crear e iniciar el servicio `systemd` (`spotify-ytm.service`) con Gunicorn en modo concurrente seguro (`1 worker`, `8 threads`).
- Configurar el VirtualHost de Apache y reiniciar el servidor web.

Al finalizar, abre tu navegador web en:
```
http://IP_DE_TU_SERVIDOR/
```

---

## 🛠️ Opción 2: Instalación Manual Paso a Paso

Si prefieres realizar el proceso manualmente:

### 1. Instalar paquetes de sistema
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip apache2
sudo a2enmod proxy proxy_http headers
```

### 2. Copiar archivos a `/var/www/`
```bash
sudo mkdir -p /var/www/spotify-to-ytm-web
sudo cp -r ./* /var/www/spotify-to-ytm-web/
```

### 3. Crear entorno virtual e instalar dependencias
```bash
cd /var/www/spotify-to-ytm-web
sudo python3 -m venv venv
sudo ./venv/bin/pip install --upgrade pip
sudo ./venv/bin/pip install -r requirements.txt
```

### 4. Configurar carpetas y permisos
```bash
sudo mkdir -p /var/www/spotify-to-ytm-web/{data,reports,uploads}
sudo chown -R www-data:www-data /var/www/spotify-to-ytm-web
sudo chmod -R 775 /var/www/spotify-to-ytm-web/{data,reports,uploads}
```

### 5. Activar el servicio systemd
```bash
sudo cp /var/www/spotify-to-ytm-web/deploy/spotify-ytm.service /etc/systemd/system/spotify-ytm.service
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-ytm.service
```

### 6. Configurar y habilitar el VirtualHost de Apache
```bash
sudo cp /var/www/spotify-to-ytm-web/deploy/apache-spotify-ytm.conf /etc/apache2/sites-available/spotify-ytm.conf
sudo a2ensite spotify-ytm.conf
sudo systemctl reload apache2
```

---

## 📋 Comandos de Mantenimiento y Control

| Acción | Comando |
|---|---|
| **Ver estado del servicio** | `sudo systemctl status spotify-ytm` |
| **Ver logs en tiempo real** | `sudo journalctl -u spotify-ytm -f` |
| **Reiniciar la aplicación** | `sudo systemctl restart spotify-ytm` |
| **Reiniciar Apache** | `sudo systemctl restart apache2` |
| **Ver logs de error de Apache** | `sudo tail -f /var/log/apache2/spotify_ytm_error.log` |

Para opciones avanzadas como configurar nombres de dominio personalizados o certificados SSL gratuitos con Let's Encrypt (Certbot), consulta el archivo **`MANUAL_DEBIAN_APACHE.md`** incluido en este paquete.
