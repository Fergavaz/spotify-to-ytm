#!/usr/bin/env python3
"""
Punto de entrada WSGI para Gunicorn y Apache mod_wsgi.
"""

import sys
import os

# Asegurar que el directorio de la aplicación esté en el path de Python
DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
if DIR_ACTUAL not in sys.path:
    sys.path.insert(0, DIR_ACTUAL)

from app import app

if __name__ == "__main__":
    app.run()
