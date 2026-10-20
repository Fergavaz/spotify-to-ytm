"""
Extracción de listas y canciones de Spotify.
Permite:
  - Extracción directa por URL de playlist (sin Premium ni API keys).
  - Búsqueda de playlists públicas por nombre de usuario / enlace de perfil.
  - Carga y parseo de archivos CSV (Exportify, Spotlistr, TuneMyMusic, etc.).
  - Consulta opcional mediante API de Spotify (spotipy).
"""

import base64
import csv
import io
import json
import re
import urllib.parse
import urllib.request

try:
    from spotify_scraper import SpotifyClient
    HAS_SCRAPER = True
except ImportError:
    HAS_SCRAPER = False


def extraer_canciones_por_url(url_o_id: str) -> tuple[str, list[dict]]:
    """
    Extrae el nombre y canciones de una playlist de Spotify mediante su URL o ID.
    Utiliza spotifyscraper con max_tracks=None para obtener todas las pistas.
    """
    if not HAS_SCRAPER:
        raise RuntimeError("La librería 'spotifyscraper' no está instalada.")

    url_limpia = url_o_id.strip().split("?")[0]
    with SpotifyClient() as client:
        playlist = client.get_playlist(url_limpia, max_tracks=None)
        nombre = getattr(playlist, "name", "Playlist Spotify")
        canciones = []
        for item in getattr(playlist, "tracks", []):
            t = getattr(item, "track", None)
            if t and getattr(t, "name", None):
                artistas = [a.name for a in getattr(t, "artists", []) if getattr(a, "name", None)]
                canciones.append({
                    "titulo": t.name,
                    "artistas": artistas,
                })
        return nombre, canciones


def buscar_playlists_usuario(usuario: str) -> list[dict]:
    """
    Obtiene las playlists públicas de un usuario de Spotify
    a partir de su ID de usuario o enlace de perfil.
    Soporta initialState codificado en base64 (Next.js/React de Spotify).
    """
    user_id = usuario.strip().strip('"').strip()

    # Si el usuario ha pegado accidentalmente una URL de playlist
    if "spotify.com/playlist/" in user_id:
        pid = user_id.split("spotify.com/playlist/")[1].split("?")[0].strip("/")
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
        req = urllib.request.Request(url_perfil, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

            # Estrategia 1: Parsear initialState (base64 o JSON plano)
            m = re.search(r'<script[^>]*id=[\x27\x22]initialState[\x27\x22][^>]*>(.*?)</script>', html)
            if m:
                raw = m.group(1).strip()
                try:
                    data = json.loads(base64.b64decode(raw).decode("utf-8")) if not raw.startswith("{") else json.loads(raw)
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

            # Estrategia 2: Regex general sobre todo el HTML para capturar cualquier playlist referenciada
            for pid in re.findall(r"playlist[:/]([a-zA-Z0-9]{22})", html):
                if pid not in vistos_ids:
                    vistos_ids.add(pid)
                    encontradas.append({
                        "id": pid,
                        "nombre": f"Playlist {pid}",
                        "url": f"https://open.spotify.com/playlist/{pid}",
                        "total": "?",
                    })
    except Exception as e:
        pass

    # Si encontramos listas y tenemos el scraper, obtenemos el total real y el nombre oficial
    if encontradas and HAS_SCRAPER:
        detalles = []
        try:
            with SpotifyClient() as client:
                for item in encontradas[:25]:
                    try:
                        pl = client.get_playlist(item["url"], max_tracks=None)
                        detalles.append({
                            "id": item["id"],
                            "nombre": pl.name,
                            "total": len(getattr(pl, "tracks", [])),
                            "url": item["url"],
                        })
                    except Exception:
                        detalles.append(item)
            return detalles
        except Exception:
            return encontradas

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
