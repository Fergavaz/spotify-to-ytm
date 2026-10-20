# Imagen base oficial de Python ligera
FROM python:3.11-slim

# Evitar que Python escriba archivos .pyc y activar salida sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

# Directorio de trabajo en el contenedor
WORKDIR /app

# Copiar el archivo de requisitos e instalar dependencias
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente de la aplicación
COPY . /app/

# Crear carpetas de datos, reportes y subidas
RUN mkdir -p /app/data /app/reports /app/uploads

# Exponer el puerto de la aplicación
EXPOSE 5000

# Comprobación de salud nativa con Python (no requiere curl ni apt-get)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/status')" || exit 1

# Comando por defecto para iniciar la aplicación con Gunicorn
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:5000", "--timeout", "120", "wsgi:app"]
