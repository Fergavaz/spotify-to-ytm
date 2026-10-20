#!/usr/bin/env python3
"""
Spotify to YouTube Music — Web Application
Servidor Flask con soporte para ejecución en segundo plano y despliegue en Apache / Debian.
"""

import json
import os
import sys
import time
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
    iniciar_flujo_oauth,
    comprobar_token_oauth,
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

    env_client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    env_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    has_env_oauth = bool(env_client_id and env_client_secret)

    return render_template(
        "index.html",
        auth_ok=auth_ok,
        auth_msg=auth_msg,
        auth_file_name=os.path.basename(auth_file) if auth_file else None,
        has_env_oauth=has_env_oauth,
        default_client_id=env_client_id,
        default_client_secret=env_client_secret,
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
    """Sube o actualiza el archivo de autenticación de YouTube Music (JSON, cabeceras en bruto o cURL)."""
    destino = os.path.join(DATA_DIR, "headers_auth.json")

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
        if not contenido:
            return jsonify({"success": False, "error": "El contenido está vacío."}), 400

        parsed = None
        # Intento 1: Es un JSON válido
        try:
            parsed = json.loads(contenido)
            if isinstance(parsed, dict):
                if "refresh_token" in parsed:
                    destino = os.path.join(DATA_DIR, "oauth.json")
                else:
                    destino = os.path.join(DATA_DIR, "headers_auth.json")
                with open(destino, "w", encoding="utf-8") as out:
                    json.dump(parsed, out, indent=2)
        except Exception:
            parsed = None

        # Intento 2: Es un comando cURL o cabeceras en bruto copiadas de DevTools
        if parsed is None:
            destino = os.path.join(DATA_DIR, "headers_auth.json")
            headers_text = contenido

            # Si es un comando cURL copiado, extraer todas las cabeceras -H '...'
            if contenido.startswith("curl") or "curl " in contenido[:20]:
                h_matches = re.findall(r"-H\s+['\"]([^'\"]+)['\"]", contenido)
                if h_matches:
                    headers_text = "\n".join(h_matches)

            try:
                from ytmusicapi.auth.browser import setup_browser
                setup_browser(filepath=destino, headers_raw=headers_text)
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"No se pudieron extraer las cabeceras requeridas. Asegúrate de copiar la petición 'browse' con sesión iniciada. Error: {str(e)}"
                }), 400
    else:
        return jsonify({"success": False, "error": "Petición no válida."}), 400

    ok, msg = verificar_autenticacion_ytm(destino)
    return jsonify({
        "success": ok,
        "message": msg,
        "auth_file": os.path.basename(destino),
    })


OAUTH_FLOWS = {}


@app.route("/api/oauth/init", methods=["POST"])
def api_oauth_init():
    """Inicia el flujo OAuth para YouTube Music con Google Device Flow."""
    data = request.get_json() or {}
    client_id = data.get("client_id", "").strip() or os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = data.get("client_secret", "").strip() or os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        return jsonify({
            "success": False,
            "error": "Debes introducir tanto el Client ID como el Client Secret de Google.",
        }), 400

    try:
        flow_data = iniciar_flujo_oauth(client_id, client_secret)
        import uuid
        session_id = uuid.uuid4().hex[:12]
        OAUTH_FLOWS[session_id] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "device_code": flow_data["device_code"],
            "user_code": flow_data["user_code"],
            "expires_at": time.time() + flow_data.get("expires_in", 1800),
            "interval": flow_data.get("interval", 5),
        }

        return jsonify({
            "success": True,
            "session_id": session_id,
            "user_code": flow_data["user_code"],
            "verification_url": flow_data["verification_url"],
            "direct_url": flow_data["direct_url"],
            "interval": flow_data.get("interval", 5),
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Error al contactar con Google OAuth: {str(e)}"}), 500


@app.route("/api/oauth/check/<session_id>", methods=["GET"])
def api_oauth_check(session_id):
    """Comprueba si el usuario ha autorizado la app en Google."""
    flow = OAUTH_FLOWS.get(session_id)
    if not flow:
        return jsonify({"success": False, "status": "error", "error": "Sesión OAuth expirada o inexistente."}), 404

    if time.time() > flow["expires_at"]:
        del OAUTH_FLOWS[session_id]
        return jsonify({"success": False, "status": "error", "error": "El código ha caducado. Vuelve a iniciar el flujo."}), 400

    ruta_oauth = os.path.join(DATA_DIR, "oauth.json")
    status, error_msg = comprobar_token_oauth(
        client_id=flow["client_id"],
        client_secret=flow["client_secret"],
        device_code=flow["device_code"],
        ruta_guardado=ruta_oauth,
    )

    if status == "success":
        del OAUTH_FLOWS[session_id]
        ok, msg = verificar_autenticacion_ytm(ruta_oauth)
        return jsonify({
            "success": True,
            "status": "success",
            "message": "¡Vinculación OAuth con Google completada con éxito! Tus credenciales se renovarán automáticamente.",
            "auth_file": "oauth.json",
        })
    elif status == "pending":
        return jsonify({
            "success": True,
            "status": "pending",
        })
    else:
        del OAUTH_FLOWS[session_id]
        return jsonify({
            "success": False,
            "status": "error",
            "error": error_msg or "Error en la autorización.",
        }), 400


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

    ok, auth_err = verificar_autenticacion_ytm(auth_file)
    if not ok:
        return jsonify({
            "success": False,
            "error": auth_err,
        }), 401

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
