#!/usr/bin/env python3
"""
Spotify to YouTube Music — Web Application
Servidor Flask con soporte para ejecución en segundo plano y despliegue en Apache / Debian.
"""

import json
import os
import sys
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from core.spotify_reader import (
    extraer_canciones_por_url,
    buscar_playlists_usuario,
    parsear_csv_spotify,
)
from core.ytm_engine import (
    encontrar_archivo_auth,
    verificar_autenticacion_ytm,
)
from core.job_runner import (
    crear_tarea,
    obtener_estado_tarea,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "spotify-to-ytm-secret-key-2026")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB max upload


@app.route("/")
def index():
    """Página principal de la aplicación web."""
    auth_file = encontrar_archivo_auth(BASE_DIR)
    auth_ok = False
    auth_msg = "No se ha encontrado archivo de autenticación (headers_auth.json / browser.json)."
    if auth_file:
        auth_ok, auth_msg = verificar_autenticacion_ytm(auth_file)

    return render_template(
        "index.html",
        auth_ok=auth_ok,
        auth_msg=auth_msg,
        auth_file_name=os.path.basename(auth_file) if auth_file else None,
    )


@app.route("/api/status", methods=["GET"])
def api_status():
    """Comprueba el estado de autenticación y servicio."""
    auth_file = encontrar_archivo_auth(BASE_DIR)
    if not auth_file:
        return jsonify({
            "authenticated": False,
            "message": "Falta archivo de autenticación de YouTube Music.",
            "auth_file": None,
        })

    ok, msg = verificar_autenticacion_ytm(auth_file)
    return jsonify({
        "authenticated": ok,
        "message": msg,
        "auth_file": os.path.basename(auth_file),
    })


@app.route("/api/upload-auth", methods=["POST"])
def api_upload_auth():
    """Sube o actualiza el archivo de autenticación de YouTube Music."""
    if "file" in request.files:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"success": False, "error": "No se seleccionó ningún archivo."}), 400
        filename = secure_filename(f.filename)
        if not filename.endswith(".json"):
            filename = "headers_auth.json"
        destino = os.path.join(DATA_DIR, filename)
        f.save(destino)
    elif request.is_json and "json_content" in request.json:
        contenido = request.json.get("json_content", "").strip()
        try:
            parsed = json.loads(contenido)
            destino = os.path.join(DATA_DIR, "headers_auth.json")
            with open(destino, "w", encoding="utf-8") as out:
                json.dump(parsed, out, indent=2)
        except Exception as e:
            return jsonify({"success": False, "error": f"JSON inválido: {str(e)}"}), 400
    else:
        return jsonify({"success": False, "error": "Petición no válida."}), 400

    ok, msg = verificar_autenticacion_ytm(destino)
    return jsonify({
        "success": ok,
        "message": msg,
        "auth_file": os.path.basename(destino),
    })


@app.route("/api/fetch-url", methods=["POST"])
def api_fetch_url():
    """Extrae las canciones de una URL de playlist de Spotify."""
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"success": False, "error": "Debes proporcionar una URL de playlist."}), 400

    try:
        nombre, canciones = extraer_canciones_por_url(url)
        if not canciones:
            return jsonify({
                "success": False,
                "error": "No se encontraron canciones. Asegúrate de que la playlist sea pública o accesible.",
            }), 404
        return jsonify({
            "success": True,
            "name": nombre,
            "count": len(canciones),
            "tracks": canciones,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al extraer la playlist: {str(e)}"}), 500


@app.route("/api/fetch-user", methods=["POST"])
def api_fetch_user():
    """Busca las playlists públicas de un usuario de Spotify."""
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"success": False, "error": "Introduce un nombre de usuario o perfil de Spotify."}), 400

    try:
        playlists = buscar_playlists_usuario(username)
        if not playlists:
            return jsonify({
                "success": False,
                "error": f"No se encontraron playlists públicas para '{username}'.",
            }), 404
        return jsonify({
            "success": True,
            "username": username,
            "playlists": playlists,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al buscar usuario: {str(e)}"}), 500


@app.route("/api/upload-csv", methods=["POST"])
def api_upload_csv():
    """Sube y procesa un archivo CSV con canciones."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No se ha subido ningún archivo."}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"success": False, "error": "Nombre de archivo vacío."}), 400

    try:
        contenido = f.read().decode("utf-8-sig", errors="ignore")
        canciones = parsear_csv_spotify(contenido)
        if not canciones:
            return jsonify({
                "success": False,
                "error": "No se pudieron reconocer columnas de canciones en el archivo CSV (se esperan 'Track Name', 'Title', 'Artist', etc.).",
            }), 400

        nombre_base = os.path.splitext(f.filename)[0]
        return jsonify({
            "success": True,
            "name": nombre_base,
            "count": len(canciones),
            "tracks": canciones,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al procesar el archivo CSV: {str(e)}"}), 500


@app.route("/api/start-transfer", methods=["POST"])
def api_start_transfer():
    """Inicia la tarea de transferencia en segundo plano."""
    data = request.get_json() or {}
    nombre = data.get("playlist_name", "").strip()
    canciones = data.get("tracks", [])
    modo_sync = bool(data.get("sync_mode", True))

    if not nombre:
        return jsonify({"success": False, "error": "El nombre de la playlist en YouTube Music es obligatorio."}), 400
    if not canciones:
        return jsonify({"success": False, "error": "La lista de canciones a transferir está vacía."}), 400

    auth_file = encontrar_archivo_auth(BASE_DIR)
    if not auth_file:
        return jsonify({
            "success": False,
            "error": "No se encontró el archivo de autenticación de YouTube Music (headers_auth.json o browser.json). Configúralo primero.",
        }), 400

    job_id = crear_tarea(
        nombre_playlist=nombre,
        canciones=canciones,
        modo_sincronizar=modo_sync,
        ruta_auth=auth_file,
        dir_reportes=REPORTS_DIR,
    )

    return jsonify({
        "success": True,
        "job_id": job_id,
        "message": "Transferencia iniciada correctamente.",
    })


@app.route("/api/job/<job_id>", methods=["GET"])
def api_get_job(job_id):
    """Devuelve el progreso y registros en tiempo real de una tarea."""
    estado = obtener_estado_tarea(job_id)
    if not estado:
        return jsonify({"success": False, "error": "Tarea no encontrada."}), 404
    return jsonify({"success": True, "job": estado})


@app.route("/api/download-report/<job_id>/<report_type>", methods=["GET"])
def api_download_report(job_id, report_type):
    """Permite descargar los CSVs de canciones no encontradas o diferencias."""
    nombres_permitidos = {
        "no_encontradas": f"{job_id}_no_encontradas.csv",
        "solo_en_spotify": f"{job_id}_solo_en_spotify.csv",
        "solo_en_ytm": f"{job_id}_solo_en_ytm.csv",
    }
    nombre_archivo = nombres_permitidos.get(report_type)
    if not nombre_archivo:
        return jsonify({"error": "Tipo de informe no válido."}), 400

    ruta = os.path.join(REPORTS_DIR, nombre_archivo)
    if not os.path.exists(ruta):
        return jsonify({"error": "El informe no existe o aún no está disponible."}), 404

    return send_file(
        ruta,
        as_attachment=True,
        download_name=f"{report_type}.csv",
        mimetype="text/csv",
    )


if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5000))
    print(f"Iniciando servidor web en http://0.0.0.0:{puerto}")
    app.run(host="0.0.0.0", port=puerto, debug=False)
