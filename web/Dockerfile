# Imagen base oficial de Python ligera
FROM python:3.11-slim

# Evitar que Python escriba archivos .pyc y activar salida sin buffer
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000

# Directorio de trabajo en el contenedor
WORKDIR /app

# Instalar dependencias del sistema necesarias (curl para healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar el archivo de requisitos e instalar dependencias
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente de la aplicación
COPY . /app/

# Crear carpetas de reportes y subidas si no existen
RUN mkdir -p /app/reports /app/uploads

# Exponer el puerto de la aplicación
EXPOSE 5000

# Comprobación de salud (Healthcheck)
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/status || exit 1

# Comando por defecto para iniciar la aplicación con Gunicorn
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:5000", "--timeout", "120", "wsgi:app"]
