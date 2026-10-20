"""
Extracción de listas y canciones de Spotify.
Permite:
  - Extracción directa por URL de playlist (sin Premium ni API keys).
  - Búsqueda de playlists públicas por nombre de usuario / enlace de perfil.
  - Carga y parseo de archivos CSV (Exportify, Spotlistr, TuneMyMusic, etc.).
  - Consulta opcional mediante API de Spotify (spotipy).
"""

import csv
import io
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
    """
    user_id = usuario.strip().strip('"').strip()
    if "spotify.com/user/" in user_id:
        user_id = user_id.split("spotify.com/user/")[1].split("?")[0].strip("/")

    encontradas = []
    vistos_ids = set()

    try:
        url_perfil = f"https://open.spotify.com/user/{urllib.parse.quote(user_id)}"
        req = urllib.request.Request(url_perfil, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            anchors = re.findall(
                r'<a [^>]*href=[\x27\x22]/playlist/([a-zA-Z0-9]{22})[\x27\x22][^>]*>(.*?)</a>',
                html,
                re.DOTALL,
            )
            for pid, content in anchors:
                if pid not in vistos_ids:
                    vistos_ids.add(pid)
                    spans = re.findall(r'<span[^>]*>(.*?)</span>', content)
                    titulo = spans[0].strip() if spans else f"Playlist {pid}"
                    encontradas.append({
                        "id": pid,
                        "nombre": titulo,
                        "url": f"https://open.spotify.com/playlist/{pid}",
                        "total": "?",
                    })
    except Exception as e:
        pass

    # Si encontramos listas y tenemos el scraper, obtenemos el total real
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
