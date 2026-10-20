"""
Motor de interacción con YouTube Music (ytmusicapi).
Maneja autenticación, búsqueda multietapa con fallback, sincronización y chunking.
"""

import json
import os
import re
import time
import urllib.parse
from typing import Callable, Optional
from ytmusicapi import YTMusic
from ytmusicapi.auth.oauth import OAuthCredentials
from core.normalizer import clave, coincide, normalizar

MAX_CANCIONES_LISTA_YTM = 5000
LOTE_API = 50
PAUSA_BUSQUEDA = 0.25


def encontrar_archivo_auth(directorio_base: str) -> Optional[str]:
    """
    Busca un archivo de autenticación válido en el directorio base o en la ruta global.
    Prioridad: headers_auth.json, browser.json (máxima compatibilidad nativa con InnerTube),
    seguido de oauth.json.
    """
    env_auth = os.environ.get("YTM_AUTH_FILE")
    if env_auth and os.path.exists(env_auth) and os.path.getsize(env_auth) > 20:
        return env_auth

    nombres = ["headers_auth.json", "browser.json", "oauth.json"]
    
    # Primera pasada: devolver el primer archivo existente que pase la verificación activa
    for nombre in nombres:
        for d in [directorio_base, os.path.join(directorio_base, "data"), os.path.dirname(directorio_base)]:
            ruta = os.path.join(d, nombre)
            if os.path.exists(ruta) and os.path.getsize(ruta) > 20:
                ok, _ = verificar_autenticacion_ytm(ruta)
                if ok:
                    return ruta

    # Segunda pasada: si ninguno pasó la prueba estricta, devolver el primer archivo existente
    for nombre in nombres:
        for d in [directorio_base, os.path.join(directorio_base, "data"), os.path.dirname(directorio_base)]:
            ruta = os.path.join(d, nombre)
            if os.path.exists(ruta) and os.path.getsize(ruta) > 20:
                return ruta
    return None


def obtener_cliente_ytm(ruta_auth: str) -> YTMusic:
    """Instancia y devuelve el cliente de YTMusic (soporta tanto OAuth como cookies)."""
    if not os.path.exists(ruta_auth):
        raise FileNotFoundError(f"No existe el archivo de autenticación: {ruta_auth}")

    try:
        with open(ruta_auth, "r", encoding="utf-8") as f:
            datos = json.load(f)
        if isinstance(datos, dict) and "refresh_token" in datos:
            cid = datos.get("client_id")
            csec = datos.get("client_secret")
            if cid and csec:
                creds = OAuthCredentials(client_id=cid, client_secret=csec)
                return YTMusic(ruta_auth, oauth_credentials=creds)
    except Exception:
        pass

    return YTMusic(ruta_auth)


def verificar_autenticacion_ytm(ruta_auth: str) -> tuple[bool, str]:
    """
    Verifica si las credenciales de YouTube Music son válidas realizando una llamada ligera.
    Comprueba permisos de lectura y estado de sesión activa.
    """
    try:
        yt = obtener_cliente_ytm(ruta_auth)
        # Comprobar llamada autenticada a la biblioteca para verificar lectura de playlists
        try:
            yt.get_library_playlists(limit=1)
        except Exception as e:
            msg = str(e).lower()
            if "unauthorized" in msg or "401" in msg or "sign in" in msg or "none" in msg:
                return False, "La sesión de YouTube Music ha caducado (Error 401). Debes renovar tu archivo headers_auth.json o browser.json."
            elif "400" in msg or "invalid argument" in msg:
                return False, "YouTube Music rechazó la petición (Error 400). Usa el método de Cabeceras / cURL (headers_auth.json)."
            return False, f"Fallo al conectar con la biblioteca de YouTube Music: {str(e)}"
        return True, "Conectado correctamente a YouTube Music."
    except Exception as e:
        return False, f"Error de autenticación en YouTube Music: {str(e)}"


def iniciar_flujo_oauth(client_id: str, client_secret: str) -> dict:
    """
    Inicia el flujo de autenticación OAuth para dispositivos Google TV / Limited Input.
    Devuelve los códigos y URL de verificación.
    """
    creds = OAuthCredentials(client_id=client_id, client_secret=client_secret)
    code_data = creds.get_code()
    if "error" in code_data:
        raise RuntimeError(f"Google OAuth error: {code_data.get('error')}")

    user_code = code_data.get("user_code")
    verification_url = code_data.get("verification_url", "https://www.google.com/device")
    direct_url = f"{verification_url}?user_code={user_code}" if user_code else verification_url
    return {
        "device_code": code_data.get("device_code"),
        "user_code": user_code,
        "verification_url": verification_url,
        "direct_url": direct_url,
        "expires_in": code_data.get("expires_in", 1800),
        "interval": code_data.get("interval", 5),
    }


def comprobar_token_oauth(
    client_id: str, client_secret: str, device_code: str, ruta_guardado: str
) -> tuple[str, Optional[str]]:
    """
    Comprueba si el usuario ha completado la autorización en Google.
    Devuelve (estado, mensaje_error):
      - 'pending', None: Aún esperando autorización
      - 'success', None: Autorizado y guardado con éxito
      - 'error', mensaje: Error o rechazo
    """
    creds = OAuthCredentials(client_id=client_id, client_secret=client_secret)
    try:
        res = creds.token_from_code(device_code)
    except Exception as e:
        return "error", str(e)

    if not isinstance(res, dict):
        return "error", "Respuesta inesperada del servidor de Google."

    if "error" in res:
        err = res["error"]
        if err in ("authorization_pending", "slow_down"):
            return "pending", None
        elif err == "access_denied":
            return "error", "Acceso denegado por el usuario en Google."
        elif err == "expired_token":
            return "error", "El código de verificación ha caducado. Vuelve a intentarlo."
        else:
            return "error", f"Error de Google OAuth: {err}"

    if "access_token" in res and "refresh_token" in res:
        try:
            token_data = {
                "access_token": res["access_token"],
                "refresh_token": res["refresh_token"],
                "scope": res.get("scope", "https://www.googleapis.com/auth/youtube"),
                "token_type": res.get("token_type", "Bearer"),
                "expires_at": int(time.time() + res.get("expires_in", 3600)),
                "expires_in": res.get("expires_in", 3600),
                "client_id": client_id,
                "client_secret": client_secret,
            }
            os.makedirs(os.path.dirname(ruta_guardado), exist_ok=True)
            with open(ruta_guardado, "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2)
            return "success", None
        except Exception as e:
            return "error", f"Error al guardar oauth.json: {str(e)}"

    return "pending", None


def en_lotes(lista: list, tam: int = LOTE_API):
    """Divide una lista en lotes de tamaño especificado."""
    for i in range(0, len(lista), tam):
        yield lista[i:i + tam]


def buscar_listas_ytm(yt: YTMusic, nombre_base: str) -> list[dict]:
    """
    Busca en YTM todas las listas que coincidan con el nombre base:
    'MiLista', 'MiLista 2', 'MiLista 3'...
    Insensible a mayúsculas/minúsculas y espacios superfluos.
    """
    todas = yt.get_library_playlists(limit=None)
    nombre_limpio = nombre_base.strip()
    patron = re.compile(rf"^{re.escape(nombre_limpio)}(\s+\d+)?$", re.IGNORECASE)
    encontradas = []
    for pl in todas:
        tit = pl.get("title", "").strip()
        if patron.match(tit):
            encontradas.append(pl)

    def orden(p):
        m = re.search(r"\s+(\d+)$", p["title"])
        return int(m.group(1)) if m else 0

    encontradas.sort(key=orden)
    return encontradas


def obtener_canciones_ytm(yt: YTMusic, playlists: list[dict], log_cb: Optional[Callable[[str], None]] = None) -> list[dict]:
    """Obtiene todas las canciones existentes en las playlists de YTM indicadas."""
    canciones = []
    for pl in playlists:
        if log_cb:
            log_cb(f"Leyendo playlist existente en YTM: '{pl['title']}'...")
        datos = yt.get_playlist(pl["playlistId"], limit=None)
        for t in datos.get("tracks", []):
            canciones.append({
                "id": t.get("videoId"),
                "titulo": t.get("title", ""),
                "artistas": [a["name"] for a in (t.get("artists") or []) if isinstance(a, dict)],
            })
    return canciones


def buscar_en_ytm(yt: YTMusic, cancion: dict) -> Optional[str]:
    """
    Busca una canción en YouTube Music y devuelve su videoId.
    Aplica búsqueda multietapa con consultas flexibles y fallback a vídeos oficiales.
    """
    artista = cancion["artistas"][0] if cancion["artistas"] else ""
    k = clave(cancion["titulo"], cancion["artistas"])
    tit_original = cancion["titulo"]

    consultas = [
        f"{tit_original} {artista}".strip(),
    ]
    sin_signos = re.sub(r"[¿?¡!]+", " ", tit_original).strip()
    if sin_signos != tit_original:
        consultas.append(f"{sin_signos} {artista}".strip())

    base_tit = normalizar(tit_original)
    if base_tit and base_tit.lower() != tit_original.lower():
        consultas.append(f"{base_tit} {artista}".strip())

    consultas = list(dict.fromkeys(c for c in consultas if c))

    # Fase 1: Canciones oficiales (filter="songs")
    for query in consultas:
        try:
            resultados = yt.search(query, filter="songs", limit=6)
            for r in resultados:
                artistas_r = [a["name"] for a in r.get("artists", []) if isinstance(a, dict)]
                if coincide(k, clave(r["title"], artistas_r), raw_a=tit_original, raw_b=r["title"]):
                    return r["videoId"]
        except Exception:
            pass

    # Fase 2: Videoclips oficiales (filter="videos")
    for query in consultas:
        try:
            resultados = yt.search(query, filter="videos", limit=6)
            for r in resultados:
                artistas_r = [a["name"] for a in r.get("artists", []) if isinstance(a, dict)]
                if coincide(k, clave(r["title"], artistas_r), raw_a=tit_original, raw_b=r["title"]):
                    return r["videoId"]
        except Exception:
            pass

    return None


def diferencia_canciones(origen: list[dict], destino: list[dict]) -> list[dict]:
    """Devuelve las canciones de 'origen' que no existen en 'destino'."""
    claves_destino = [clave(t["titulo"], t["artistas"]) for t in destino]
    faltan = []
    for t in origen:
        k = clave(t["titulo"], t["artistas"])
        if not any(coincide(k, c) for c in claves_destino):
            faltan.append(t)
    return faltan


def planificar_transferencia(
    yt: YTMusic,
    nombre_playlist: str,
    canciones_spotify: list[dict],
    modo_sync: bool,
) -> dict:
    """
    Simula y analiza qué ocurrirá en YouTube Music antes de ejecutar la transferencia:
    - Si existe una o más listas coincidentes y modo_sync está activado:
      Calcula exactamente qué canciones faltan y cuáles ya están presentes.
    - Si no existe lista: indica que se creará una nueva y se añadirán todas.
    """
    nombre_limpio = nombre_playlist.strip()
    listas_existentes = buscar_listas_ytm(yt, nombre_limpio)

    if listas_existentes and modo_sync:
        canciones_ytm = obtener_canciones_ytm(yt, listas_existentes)
        claves_ytm = [clave(t["titulo"], t["artistas"]) for t in canciones_ytm]
        claves_sp = [clave(t["titulo"], t["artistas"]) for t in canciones_spotify]

        canciones_a_anadir = []
        canciones_ya_en_ytm = []
        for t in canciones_spotify:
            k = clave(t["titulo"], t["artistas"])
            if any(coincide(k, c) for c in claves_ytm):
                canciones_ya_en_ytm.append(t)
            else:
                canciones_a_anadir.append(t)

        # Detectar canciones que están en YTM pero NO en Spotify
        solo_en_ytm = []
        for t in canciones_ytm:
            k = clave(t["titulo"], t["artistas"])
            if not any(coincide(k, c) for c in claves_sp):
                q = f"{t['titulo']} {' '.join(t['artistas'])}".strip()
                solo_en_ytm.append({
                    "id": t.get("id"),
                    "titulo": t["titulo"],
                    "artistas": t["artistas"],
                    "spotify_search_url": f"https://open.spotify.com/search/{urllib.parse.quote(q)}",
                    "ytm_url": f"https://music.youtube.com/watch?v={t['id']}" if t.get("id") else None,
                })

        nombres_existentes = [p["title"] for p in listas_existentes]

        partes_msg = []
        if canciones_a_anadir:
            partes_msg.append(
                f"Se sincronizará con la playlist existente '{nombres_existentes[0]}' en YouTube Music: "
                f"se añadirá(n) {len(canciones_a_anadir)} canción(es) nueva(s) y se omitirá(n) {len(canciones_ya_en_ytm)} que ya existen."
            )
        else:
            partes_msg.append(
                f"¡Tu playlist '{nombres_existentes[0]}' en YouTube Music ya tiene todas las canciones de Spotify!"
            )

        if solo_en_ytm:
            partes_msg.append(
                f"Además, se han detectado {len(solo_en_ytm)} canciones en YouTube Music que no están en la lista original de Spotify."
            )

        return {
            "existe_en_ytm": True,
            "tipo_accion": "sincronizar",
            "listas_existentes": nombres_existentes,
            "total_actual_ytm": len(canciones_ytm),
            "total_spotify": len(canciones_spotify),
            "total_a_anadir": len(canciones_a_anadir),
            "total_ya_existentes": len(canciones_ya_en_ytm),
            "total_solo_en_ytm": len(solo_en_ytm),
            "canciones_a_anadir": canciones_a_anadir,
            "canciones_ya_existentes": canciones_ya_en_ytm,
            "canciones_solo_en_ytm": solo_en_ytm,
            "mensaje": " ".join(partes_msg),
        }
    else:
        if listas_existentes:
            msg = (
                f"Modo sincronización desactivado. Aunque ya existe '{nombre_limpio}', se creará una "
                f"nueva lista independiente en YouTube Music con las {len(canciones_spotify)} canciones."
            )
        else:
            msg = (
                f"No existe ninguna playlist llamada '{nombre_limpio}' en tu biblioteca de YouTube Music. "
                f"Se creará como una nueva lista y se añadirán las {len(canciones_spotify)} canciones."
            )

        return {
            "existe_en_ytm": bool(listas_existentes),
            "tipo_accion": "crear_nueva",
            "listas_existentes": [p["title"] for p in listas_existentes] if listas_existentes else [],
            "total_actual_ytm": 0,
            "total_spotify": len(canciones_spotify),
            "total_a_anadir": len(canciones_spotify),
            "total_ya_existentes": 0,
            "total_solo_en_ytm": 0,
            "canciones_a_anadir": canciones_spotify,
            "canciones_ya_existentes": [],
            "canciones_solo_en_ytm": [],
            "mensaje": msg,
        }


def calcular_nombre_lista(nombre_base: str, indice: int) -> str:
    """Genera el nombre de lista: 'MiLista', 'MiLista 2', 'MiLista 3'..."""
    if indice <= 1:
        return nombre_base
    return f"{nombre_base} {indice}"


def obtener_capacidad_listas(yt: YTMusic, listas_existentes: list[dict]) -> list[dict]:
    """Devuelve las listas con su capacidad disponible (hasta 5000 canciones)."""
    info = []
    for pl in listas_existentes:
        datos = yt.get_playlist(pl["playlistId"], limit=None)
        total = len(datos.get("tracks", []))
        info.append({
            "playlistId": pl["playlistId"],
            "title": pl["title"],
            "total_actual": total,
            "espacio_libre": max(0, MAX_CANCIONES_LISTA_YTM - total),
        })
    return info


def anadir_canciones_ytm(
    yt: YTMusic,
    nombre_base: str,
    video_ids: list[str],
    listas_existentes: list[dict],
    log_cb: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """
    Añade los video_ids a las listas de YTM.
    Llena listas existentes hasta el límite de 5000 y crea nuevas si es necesario.
    Devuelve la lista de nombres de playlists creadas o actualizadas.
    """
    if not video_ids:
        return []

    info_listas = obtener_capacidad_listas(yt, listas_existentes) if listas_existentes else []
    ids_pendientes = list(video_ids)
    listas_modificadas = []

    # 1. Rellenar listas existentes con espacio libre
    for lista in info_listas:
        if not ids_pendientes:
            break
        if lista["espacio_libre"] > 0:
            lote_total = ids_pendientes[:lista["espacio_libre"]]
            ids_pendientes = ids_pendientes[lista["espacio_libre"]:]
            if log_cb:
                log_cb(f"Añadiendo {len(lote_total)} canciones a la lista existente '{lista['title']}'...")
            for lote in en_lotes(lote_total):
                yt.add_playlist_items(lista["playlistId"], videoIds=lote, duplicates=True)
                time.sleep(PAUSA_BUSQUEDA)
            listas_modificadas.append(lista["title"])

    # 2. Si quedan canciones, crear nuevas listas numeradas
    if ids_pendientes:
        if listas_existentes:
            numeros = []
            for pl in listas_existentes:
                m = re.search(r"\s+(\d+)$", pl["title"])
                numeros.append(int(m.group(1)) if m else 1)
            siguiente = max(numeros) + 1
        else:
            siguiente = 1

        while ids_pendientes:
            nombre_nueva = calcular_nombre_lista(nombre_base, siguiente)
            lote_total = ids_pendientes[:MAX_CANCIONES_LISTA_YTM]
            ids_pendientes = ids_pendientes[MAX_CANCIONES_LISTA_YTM:]

            if log_cb:
                log_cb(f"Creando nueva lista '{nombre_nueva}' con {len(lote_total)} canciones...")

            primer_lote = lote_total[:LOTE_API]
            pl_id = yt.create_playlist(
                title=nombre_nueva,
                description=f"Transferida desde Spotify — {nombre_base}",
                video_ids=primer_lote,
            )
            for lote in en_lotes(lote_total[LOTE_API:]):
                yt.add_playlist_items(pl_id, videoIds=lote, duplicates=True)
                time.sleep(PAUSA_BUSQUEDA)

            listas_modificadas.append(nombre_nueva)
            siguiente += 1

    return listas_modificadas
