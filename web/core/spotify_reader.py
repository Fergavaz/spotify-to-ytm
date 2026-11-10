"""
Extracción nativa y resiliente de listas y canciones de Spotify.
Permite:
  - Extracción directa por URL de playlist (sin Premium ni API keys).
  - Paginación completa de canciones mediante la API interna Pathfinder de Spotify.
  - Búsqueda de playlists públicas por nombre de usuario con conteo real de canciones.
  - Carga y parseo de archivos CSV (Exportify, Spotlistr, TuneMyMusic, etc.).
"""
from __future__ import annotations

import base64
import csv
import io
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Optional

PATHFINDER_HASH = "a65e12194ed5fc443a1cdebed5fabe33ca5b07b987185d63c72483867ad13cb4"
HEADERS_BASE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}

_TOKEN_CACHE: dict[str, any] = {
    "token": None,
    "expires_at": 0,
}


def _obtener_token_spotify(sample_id: str = "37i9dQZF1DXcBWIGoYBM5M") -> str:
    """
    Obtiene un token de sesión anónimo desde la página de embed de Spotify.
    Se cachea en memoria hasta su expiración para minimizar peticiones.
    """
    ahora = time.time()
    if _TOKEN_CACHE["token"] and ahora < _TOKEN_CACHE["expires_at"] - 60:
        return _TOKEN_CACHE["token"]

    embed_url = f"https://open.spotify.com/embed/playlist/{sample_id}"
    req = urllib.request.Request(embed_url, headers=HEADERS_BASE)
    with urllib.request.urlopen(req, timeout=12) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    m = re.search(r'<script id=[\x27\x22]__NEXT_DATA__[\x27\x22][^>]*>(.*?)</script>', html)
    if not m:
        raise RuntimeError("No se pudo obtener el bloque __NEXT_DATA__ de Spotify embed.")

    data = json.loads(m.group(1))
    session = data.get("props", {}).get("pageProps", {}).get("state", {}).get("settings", {}).get("session", {})
    token = session.get("accessToken")
    expires_ms = session.get("accessTokenExpirationTimestampMs", 0)

    if not token:
        raise RuntimeError("No se encontró accessToken en la sesión embed de Spotify.")

    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = (expires_ms / 1000.0) if expires_ms else ahora + 3600
    return token


def _extraer_id_playlist(url_o_id: str) -> str:
    """Extrae el ID alfanumérico de 22 caracteres de una playlist."""
    t = url_o_id.strip()
    m = re.search(r"playlist[:/]([a-zA-Z0-9]{22})", t)
    if m:
        return m.group(1)
    if len(t) == 22 and t.isalnum():
        return t
    return t.split("?")[0].strip("/")


def _extraer_via_pathfinder(playlist_id: str, token: str) -> tuple[str, list[dict]]:
    """
    Extrae la playlist paginando por lotes de 100 canciones
    mediante el endpoint GraphQL Pathfinder oficial del Web Player de Spotify.
    """
    offset = 0
    limit = 100
    canciones: list[dict] = []
    nombre_playlist = "Playlist Spotify"

    while True:
        vars_payload = {
            "uri": f"spotify:playlist:{playlist_id}",
            "offset": offset,
            "limit": limit,
            "enableWatchFeedEntrypoint": False,
        }
        ext_payload = {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": PATHFINDER_HASH,
            }
        }
        url = (
            f"https://api-partner.spotify.com/pathfinder/v1/query?"
            f"operationName=fetchPlaylist&"
            f"variables={urllib.parse.quote(json.dumps(vars_payload))}&"
            f"extensions={urllib.parse.quote(json.dumps(ext_payload))}"
        )

        req = urllib.request.Request(
            url,
            headers={
                **HEADERS_BASE,
                "Authorization": f"Bearer {token}",
                "app-platform": "WebPlayer",
            },
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        pl_data = data.get("data", {}).get("playlistV2", {})
        if pl_data.get("name"):
            nombre_playlist = pl_data["name"]

        content = pl_data.get("content", {})
        total_count = content.get("totalCount", 0)
        items = content.get("items", [])

        if not items:
            break

        for item in items:
            t = item.get("itemV2", {}).get("data", {})
            if t.get("__typename") == "Track" and t.get("name"):
                artistas = [
                    a.get("profile", {}).get("name")
                    for a in t.get("artists", {}).get("items", [])
                    if a.get("profile", {}).get("name")
                ]
                canciones.append({
                    "titulo": t["name"],
                    "artistas": artistas,
                })

        offset += len(items)
        if total_count and offset >= total_count:
            break

    return nombre_playlist, canciones


def _extraer_via_embed(playlist_id: str) -> tuple[str, list[dict]]:
    """
    Fallback secundario: Extrae las canciones directamente del HTML embed
    (hasta 100 pistas).
    """
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
    req = urllib.request.Request(embed_url, headers=HEADERS_BASE)
    with urllib.request.urlopen(req, timeout=12) as resp:
        html = resp.read().decode("utf-8", errors="ignore")

    m = re.search(r'<script id=[\x27\x22]__NEXT_DATA__[\x27\x22][^>]*>(.*?)</script>', html)
    if not m:
        return "Playlist Spotify", []

    data = json.loads(m.group(1))
    entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
    nombre = entity.get("name") or entity.get("title") or "Playlist Spotify"
    canciones: list[dict] = []

    for item in entity.get("trackList", []):
        titulo = item.get("title")
        sub = item.get("subtitle") or ""
        artistas = [a.strip() for a in sub.split(",") if a.strip()]
        if titulo:
            canciones.append({
                "titulo": titulo,
                "artistas": artistas,
            })

    return nombre, canciones


def extraer_canciones_por_url(url_o_id: str) -> tuple[str, list[dict]]:
    """
    Extrae el nombre y todas las canciones de una playlist de Spotify mediante su URL o ID.
    Utiliza el motor Pathfinder nativo con paginación completa (sin límites de 100).
    """
    pid = _extraer_id_playlist(url_o_id)
    if not pid:
        raise ValueError(f"No se pudo reconocer un ID de playlist válido en: {url_o_id}")

    # Estrategia 1: Pathfinder nativo con token anónimo
    try:
        token = _obtener_token_spotify(pid)
        nombre, canciones = _extraer_via_pathfinder(pid, token)
        if canciones:
            return nombre, canciones
    except Exception:
        pass

    # Estrategia 2: Fallback al embed HTML directo
    try:
        nombre, canciones = _extraer_via_embed(pid)
        if canciones:
            return nombre, canciones
    except Exception as e:
        raise RuntimeError(f"Error al extraer la playlist de Spotify: {e}")

    raise RuntimeError("No se pudieron extraer canciones de la playlist especificada.")


def buscar_playlists_usuario(usuario: str) -> list[dict]:
    """
    Obtiene las playlists públicas de un usuario de Spotify
    a partir de su ID de usuario o enlace de perfil.
    Calcula el conteo real de canciones de cada lista pública encontrada.
    """
    user_id = usuario.strip().strip('"').strip()

    # Si el usuario ha pegado accidentalmente una URL de playlist
    if "spotify.com/playlist/" in user_id:
        pid = _extraer_id_playlist(user_id)
        try:
            nombre, pistas = extraer_canciones_por_url(user_id)
            return [{
                "id": pid,
                "nombre": nombre,
                "url": f"https://open.spotify.com/playlist/{pid}",
                "total": len(pistas),
            }]
        except Exception:
            pass

    if "spotify.com/user/" in user_id:
        user_id = user_id.split("spotify.com/user/")[1].split("?")[0].strip("/")
    elif "?" in user_id:
        user_id = user_id.split("?")[0].strip("/")

    encontradas = []
    vistos_ids = set()

    try:
        url_perfil = f"https://open.spotify.com/user/{urllib.parse.quote(user_id)}"
        req = urllib.request.Request(url_perfil, headers=HEADERS_BASE)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Estrategia 1: Parsear initialState (base64 o JSON plano)
        m = re.search(r'<script[^>]*id=[\x27\x22]initialState[\x27\x22][^>]*>(.*?)</script>', html)
        if m:
            raw = m.group(1).strip()
            try:
                data = json.loads(raw) if raw.startswith("{") else json.loads(base64.b64decode(raw).decode("utf-8"))
                items_dict = data.get("entities", {}).get("items", {})
                for v in items_dict.values():
                    if not isinstance(v, dict):
                        continue
                    for pl_key in ("publicPlaylistsV2", "publicPlaylists"):
                        for item in v.get(pl_key, {}).get("items", []):
                            uri = item.get("_uri") or item.get("uri") or item.get("data", {}).get("uri") or ""
                            name = item.get("data", {}).get("name") or item.get("name") or "Playlist"
                            m_id = re.search(r"playlist[:/]([a-zA-Z0-9]{22})", uri)
                            if m_id and m_id.group(1) not in vistos_ids:
                                pid = m_id.group(1)
                                vistos_ids.add(pid)
                                encontradas.append({
                                    "id": pid,
                                    "nombre": name,
                                    "url": f"https://open.spotify.com/playlist/{pid}",
                                    "total": "?",
                                })
            except Exception:
                pass

        # Estrategia 2: Regex general sobre todo el HTML
        for pid in re.findall(r"playlist[:/]([a-zA-Z0-9]{22})", html):
            if pid not in vistos_ids:
                vistos_ids.add(pid)
                encontradas.append({
                    "id": pid,
                    "nombre": f"Playlist {pid}",
                    "url": f"https://open.spotify.com/playlist/{pid}",
                    "total": "?",
                })
    except Exception:
        pass

    # Si encontramos listas, enriquecemos el conteo real de canciones con Pathfinder
    if encontradas:
        try:
            token = _obtener_token_spotify(encontradas[0]["id"])
            for item in encontradas[:25]:
                try:
                    pid = item["id"]
                    vars_payload = {
                        "uri": f"spotify:playlist:{pid}",
                        "offset": 0,
                        "limit": 1,
                        "enableWatchFeedEntrypoint": False,
                    }
                    ext_payload = {
                        "persistedQuery": {
                            "version": 1,
                            "sha256Hash": PATHFINDER_HASH,
                        }
                    }
                    url = (
                        f"https://api-partner.spotify.com/pathfinder/v1/query?"
                        f"operationName=fetchPlaylist&"
                        f"variables={urllib.parse.quote(json.dumps(vars_payload))}&"
                        f"extensions={urllib.parse.quote(json.dumps(ext_payload))}"
                    )
                    req_pf = urllib.request.Request(
                        url,
                        headers={
                            **HEADERS_BASE,
                            "Authorization": f"Bearer {token}",
                            "app-platform": "WebPlayer",
                        },
                    )
                    with urllib.request.urlopen(req_pf, timeout=5) as r:
                        res = json.loads(r.read().decode("utf-8"))
                        pl = res.get("data", {}).get("playlistV2", {})
                        if pl.get("name"):
                            item["nombre"] = pl["name"]
                        tot = pl.get("content", {}).get("totalCount")
                        if tot is not None:
                            item["total"] = tot
                except Exception:
                    pass
        except Exception:
            pass

    return encontradas


def parsear_csv_spotify(contenido_csv: str) -> list[dict]:
    """
    Parsea el contenido de un archivo CSV de Spotify (Exportify, Soundiiz, etc.)
    y devuelve una lista de diccionarios con {'titulo': ..., 'artistas': [...]}.
    """
    f = io.StringIO(contenido_csv)
    lector = csv.DictReader(f)
    pistas = []
    for fila in lector:
        titulo = (
            fila.get("Track Name")
            or fila.get("Title")
            or fila.get("titulo")
            or fila.get("name")
            or fila.get("Track")
        )
        artista = (
            fila.get("Artist Name(s)")
            or fila.get("Artist")
            or fila.get("artistas")
            or fila.get("artist")
            or fila.get("Artists")
        )
        if titulo:
            artistas = [a.strip() for a in artista.split(",")] if artista else []
            pistas.append({
                "titulo": titulo.strip(),
                "artistas": artistas,
            })
    return pistas
