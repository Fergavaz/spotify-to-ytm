# 🚀 Guía de Instalación en Debian con Apache
## Dominio: `y2s.fergavaz.duckdns.org`
## Ruta: `/var/www/html/y2s`

Este paquete contiene todo el código y configuración necesarios para servir **Spotify to YouTube Music** como una aplicación web nativa en **Debian GNU/Linux** con **Apache2** y **Gunicorn** (sin Docker).

---

## ⚡ Opción 1: Instalación Automática en 1 Paso (Recomendada)

1. Sube y descomprime el archivo `.zip` en tu servidor Debian (por ejemplo en tu carpeta de usuario o temporal):
   ```bash
   unzip spotify-to-ytm-debian.zip -d y2s_temp
   cd y2s_temp/spotify-to-ytm-web
   ```

2. Dale permisos de ejecución al script de instalación y ejecútalo como root:
   ```bash
   chmod +x deploy/install_debian.sh
   sudo ./deploy/install_debian.sh
   ```

El script se encargará automáticamente de:
- Instalar Apache2, Python 3, venv y los módulos de proxy inverso (`proxy`, `proxy_http`, `headers`).
- Copiar la aplicación a `/var/www/html/y2s/`.
- Crear el entorno virtual `venv` e instalar todas las dependencias (`requirements.txt`).
- Configurar y activar el servicio `systemd` (`spotify-ytm.service`) con Gunicorn en modo concurrente seguro (`1 worker`, `8 threads`, `timeout 120s`).
- Configurar el VirtualHost de Apache para `y2s.fergavaz.duckdns.org` y recargar el servidor web.

Al finalizar, abre tu navegador web en:
```
http://y2s.fergavaz.duckdns.org/
```

---

## 🔒 Certificado SSL / HTTPS Gratuito con Let's Encrypt

Una vez que el VirtualHost esté activo y el dominio `y2s.fergavaz.duckdns.org` apunte a la IP de tu servidor, puedes activar HTTPS en 1 comando:

```bash
sudo apt install -y certbot python3-certbot-apache
sudo certbot --apache -d y2s.fergavaz.duckdns.org
```

Certbot actualizará automáticamente la configuración de Apache para redirigir todo el tráfico a HTTPS de forma segura.

---

## 🛠️ Opción 2: Instalación Manual Paso a Paso

### 1. Instalar paquetes de sistema
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip apache2
sudo a2enmod proxy proxy_http headers
```

### 2. Copiar archivos a `/var/www/html/y2s`
```bash
sudo mkdir -p /var/www/html/y2s
sudo cp -r ./* /var/www/html/y2s/
```

### 3. Crear entorno virtual e instalar dependencias
```bash
cd /var/www/html/y2s
sudo python3 -m venv venv
sudo ./venv/bin/pip install --upgrade pip
sudo ./venv/bin/pip install -r requirements.txt
```

### 4. Configurar carpetas y permisos para `www-data`
```bash
sudo mkdir -p /var/www/html/y2s/{data,reports,uploads}
sudo chown -R www-data:www-data /var/www/html/y2s
sudo chmod -R 775 /var/www/html/y2s/{data,reports,uploads}
```

### 5. Activar el servicio systemd
```bash
sudo cp /var/www/html/y2s/deploy/spotify-ytm.service /etc/systemd/system/spotify-ytm.service
sudo systemctl daemon-reload
sudo systemctl enable --now spotify-ytm.service
```

### 6. Configurar y habilitar el VirtualHost en Apache
```bash
sudo cp /var/www/html/y2s/deploy/y2s.fergavaz.duckdns.org.conf /etc/apache2/sites-available/y2s.fergavaz.duckdns.org.conf
sudo a2ensite y2s.fergavaz.duckdns.org.conf
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
| **Ver logs de error de Apache** | `sudo tail -f /var/log/apache2/y2s_error.log` |
