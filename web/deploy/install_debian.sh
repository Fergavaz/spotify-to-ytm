#!/usr/bin/env bash
# ==============================================================================
# Script de Instalación Automatizada para Debian Linux
# Spotify to YouTube Music — Web Application
# Dominio: y2s.fergavaz.duckdns.org
# Ruta de instalación: /var/www/html/y2s
# ==============================================================================
set -e

# Comprobar privilegios de root / sudo
if [ "$EUID" -ne 0 ]; then
  echo "❌ Por favor, ejecuta este script con permisos de root (sudo ./install_debian.sh)"
  exit 1
fi

APP_DIR="/var/www/html/y2s"
DOMAIN="y2s.fergavaz.duckdns.org"
SCRIPT_SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🚀 Iniciando instalación de Spotify to YouTube Music Web en Debian..."
echo "📍 Destino: ${APP_DIR}"
echo "🌐 Dominio: ${DOMAIN}"

# 1. Actualizar repositorios e instalar paquetes del sistema
echo "📦 [1/6] Instalando dependencias de Debian y Apache..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip apache2 curl

# 2. Habilitar módulos de proxy en Apache
echo "⚙️  [2/6] Habilitando módulos de Apache (proxy, proxy_http, headers)..."
a2enmod proxy proxy_http headers

# 3. Copiar la aplicación a /var/www/html/y2s
if [ "${SCRIPT_SRC_DIR}" != "${APP_DIR}" ]; then
  echo "📁 [3/6] Copiando archivos a ${APP_DIR}..."
  mkdir -p "${APP_DIR}"
  cp -r "${SCRIPT_SRC_DIR}"/* "${APP_DIR}/"
else
  echo "📁 [3/6] La aplicación ya reside en ${APP_DIR}."
fi

# 4. Crear entorno virtual de Python e instalar requisitos
echo "🐍 [4/6] Creando entorno virtual e instalando librerías Python..."
python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/pip" install --upgrade pip
"${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

# 5. Configurar servicio systemd para Gunicorn
echo "🛠️  [5/6] Instalando y activando servicio systemd..."
cp "${APP_DIR}/deploy/spotify-ytm.service" /etc/systemd/system/spotify-ytm.service
systemctl daemon-reload
systemctl enable spotify-ytm.service
systemctl restart spotify-ytm.service

# 6. Configurar VirtualHost en Apache
echo "🌐 [6/6] Configurando VirtualHost en Apache..."
cp "${APP_DIR}/deploy/y2s.fergavaz.duckdns.org.conf" "/etc/apache2/sites-available/${DOMAIN}.conf"
a2ensite "${DOMAIN}.conf"
systemctl reload apache2

# Ajustar permisos para www-data
mkdir -p "${APP_DIR}/data" "${APP_DIR}/reports" "${APP_DIR}/uploads"
chown -R www-data:www-data "${APP_DIR}"
chmod -R 775 "${APP_DIR}/data" "${APP_DIR}/reports" "${APP_DIR}/uploads"

echo ""
echo "=============================================================================="
echo "✅ ¡Instalación completada con éxito!"
echo "=============================================================================="
echo "La aplicación está corriendo en segundo plano gestionada por systemd y Apache."
echo "Puedes acceder desde tu navegador en:"
echo "   http://${DOMAIN}/"
echo ""
echo "💡 Para habilitar SSL/HTTPS gratuito con Let's Encrypt:"
echo "   sudo apt install -y certbot python3-certbot-apache"
echo "   sudo certbot --apache -d ${DOMAIN}"
echo ""
echo "Comandos útiles:"
echo "   Ver estado de la app:   systemctl status spotify-ytm"
echo "   Ver logs en vivo:       journalctl -u spotify-ytm -f"
echo "   Reiniciar app:          systemctl restart spotify-ytm"
echo "   Reiniciar Apache:       systemctl reload apache2"
echo "=============================================================================="
