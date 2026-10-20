#!/usr/bin/env python3
"""
spotify_to_ytm.py
─────────────────
Transfiere una playlist de Spotify a YouTube Music.

Flujo:
  1. Conecta con Spotify (API o extracción directa por URL/enlace o CSV).
     - No requiere Spotify Premium: permite transferir pegando el enlace
       directo de la playlist de Spotify (ej: https://open.spotify.com/playlist/...)
       o conectando por API si se dispone de cuenta Developer.
     - Guarda credenciales de forma cifrada en spotify_config.enc.
  2. Solicita la playlist de Spotify a transferir.
  3. Busca en YTM si ya existe una lista con el mismo nombre.
  4. Compara ambas listas y detecta las canciones que faltan.
  5. Añade las canciones faltantes a la lista de YTM.
  6. Si la lista supera las 5000 canciones (límite de YTM), reparte
     en listas numeradas: "MiLista", "MiLista 2", "MiLista 3", etc.
"""

import base64
import csv
import difflib
import getpass
import hashlib
import json
import os
import platform
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from cryptography.fernet import Fernet, InvalidToken
from ytmusicapi import YTMusic

try:
    from spotify_scraper import SpotifyClient
    HAS_SCRAPER = True
except ImportError:
    HAS_SCRAPER = False

# ─── Constantes ──────────────────────────────────────────────────────────────
MAX_CANCIONES_LISTA_YTM = 5000
LOTE_API = 50  # Canciones por llamada a la API (evita errores de payload)
UMBRAL_SIMILITUD = 0.88
PAUSA_BUSQUEDA = 0.3  # Segundos entre búsquedas para no saturar la API


def en_lotes(lista: list, tam: int = LOTE_API):
    """Divide una lista en lotes del tamaño indicado."""
    for i in range(0, len(lista), tam):
        yield lista[i:i + tam]


# ═══════════════════════════════════════════════════════════════════════════════
# NORMALIZACIÓN Y COMPARACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def _limpiar_cadena(texto: str) -> str:
    """Elimina acentos, puntuación irrelevante y términos superfluos."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    t = t.lower()
    # Eliminar paréntesis y corchetes (remixes, live, etc.)
    t = re.sub(r"[\(\[].*?[\)\]]", " ", t)
    # Eliminar colaboraciones tipo feat, ft, con, with
    t = re.sub(r"\b(feat|ft|con|with)\b.*$", " ", t)
    # Eliminar términos de formato habituales
    t = re.sub(
        r"\b(video oficial|videoclip oficial|videoclip|video clip|audio oficial|lyric video|"
        r"official video|official audio|video lyric|bonus track|remaster(ed)?|remasterizado|version|edicion.*|deluxe)\b",
        " ", t,
    )
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalizar(texto: str) -> str:
    """Limpia y normaliza la parte principal del título."""
    t = texto or ""
    if " - " in t:
        t = t.split(" - ")[0]
    return _limpiar_cadena(t)


def normalizar_candidatos(texto: str) -> list[str]:
    """
    Genera candidatos de normalización para títulos complejos o formatos de vídeo
    (ej: 'Valiente Bosque - ¿A Dónde Vamos?' -> ['a donde vamos', 'valiente bosque']).
    """
    candidatos = [_limpiar_cadena(texto)]
    if " - " in texto:
        partes = texto.split(" - ")
        candidatos.append(_limpiar_cadena(partes[0]))
        if len(partes) > 1:
            candidatos.append(_limpiar_cadena(partes[1]))
    return list(dict.fromkeys(c for c in candidatos if c))


def clave(titulo: str, artistas: list[str]) -> tuple[str, str]:
    """Genera clave normalizada (titulo_base, primer_artista)."""
    primero = artistas[0] if artistas else ""
    return normalizar(titulo), _limpiar_cadena(primero)


def coincide(a: tuple[str, str], b: tuple[str, str], raw_a: str = "", raw_b: str = "") -> bool:
    """
    Comprueba con flexibilidad si dos canciones corresponden a la misma pista.
    Soporta títulos con remixes, remasterizaciones, vídeos oficiales y orden Artista - Título.
    """
    if a == b:
        return True

    # 1. Comprobación directa
    sim_titulo = difflib.SequenceMatcher(None, a[0], b[0]).ratio()
    tit_ok = (
        sim_titulo >= 0.82
        or (len(a[0]) >= 4 and a[0] in b[0])
        or (len(b[0]) >= 4 and b[0] in a[0])
    )

    # 2. Si no coincide directo, comprobar candidatos derivados de los títulos sin recortar
    if not tit_ok:
        texto_a = raw_a if raw_a else a[0]
        texto_b = raw_b if raw_b else b[0]
        cands_a = normalizar_candidatos(texto_a)
        cands_b = normalizar_candidatos(texto_b)
        for ca in cands_a:
            for cb in cands_b:
                sim = difflib.SequenceMatcher(None, ca, cb).ratio()
                if sim >= 0.82 or (len(ca) >= 4 and ca in cb) or (len(cb) >= 4 and cb in ca):
                    tit_ok = True
                    break
            if tit_ok:
                break

    if not tit_ok:
        return False

    # Si falta el artista en alguno de los dos lados, confiamos en el título
    if not a[1] or not b[1]:
        return True

    # Comprobación del artista (o si el artista está contenido en el título del vídeo)
    art_ok = (
        difflib.SequenceMatcher(None, a[1], b[1]).ratio() >= 0.78
        or a[1] in b[1]
        or b[1] in a[1]
        or (len(a[1]) >= 4 and a[1] in b[0])
        or (len(b[1]) >= 4 and b[1] in a[0])
        or (raw_b and len(a[1]) >= 4 and a[1] in _limpiar_cadena(raw_b))
        or (raw_a and len(b[1]) >= 4 and b[1] in _limpiar_cadena(raw_a))
    )
    return art_ok


# ═══════════════════════════════════════════════════════════════════════════════
# GESTIÓN DE CREDENCIALES (cifrado Fernet / AES-128-CBC)
# ═══════════════════════════════════════════════════════════════════════════════

def _dir_script() -> str:
    """Devuelve la carpeta donde reside el script."""
    return os.path.dirname(os.path.abspath(__file__))


def _derivar_clave() -> bytes:
    """
    Genera una clave Fernet determinista ligada al usuario y la máquina.
    No se almacena en ningún fichero: se recalcula cada vez.
    """
    semilla = f"{getpass.getuser()}@{platform.node()}::spotify_to_ytm_v1"
    clave = hashlib.pbkdf2_hmac(
        "sha256",
        semilla.encode("utf-8"),
        b"spotify_to_ytm_salt_2024",
        iterations=150_000,
    )
    return base64.urlsafe_b64encode(clave)


def _ruta_config() -> str:
    """Ruta del archivo de configuración cifrado."""
    return os.path.join(_dir_script(), "spotify_config.enc")


def cargar_credenciales() -> dict | None:
    """
    Carga y descifra las credenciales de Spotify.
    Devuelve {"client_id": ..., "client_secret": ...} o None.
    """
    ruta = _ruta_config()
    if not os.path.exists(ruta):
        return None
    try:
        fernet = Fernet(_derivar_clave())
        with open(ruta, "rb") as f:
            datos_cifrados = f.read()
        datos_json = fernet.decrypt(datos_cifrados)
        creds = json.loads(datos_json)
        if creds.get("client_id") and creds.get("client_secret"):
            return creds
        return None
    except (InvalidToken, json.JSONDecodeError, Exception):
        return None


def guardar_credenciales(client_id: str, client_secret: str) -> None:
    """Cifra y guarda las credenciales de Spotify en spotify_config.enc."""
    ruta = _ruta_config()
    datos = json.dumps({
        "client_id": client_id,
        "client_secret": client_secret,
    })
    fernet = Fernet(_derivar_clave())
    with open(ruta, "wb") as f:
        f.write(fernet.encrypt(datos.encode("utf-8")))
    print(f"   🔒 Credenciales guardadas cifradas en: {os.path.basename(ruta)}")


def solicitar_credenciales() -> tuple[str, str]:
    """Solicita las credenciales de Spotify al usuario."""
    print("\n🔑 Configuración de credenciales de Spotify")
    print("   Obtenlas en: https://developer.spotify.com/dashboard")
    print("   (Crea una app → Settings → Client ID / Client Secret)\n")
    client_id = input("   Client ID: ").strip()
    client_secret = input("   Client Secret: ").strip()
    if not client_id or not client_secret:
        sys.exit("❌ Ambos campos son obligatorios.")
    return client_id, client_secret


def borrar_cache_spotify() -> None:
    """Elimina el archivo .cache de spotipy (tokens antiguos)."""
    cache = os.path.join(_dir_script(), ".cache")
    if os.path.exists(cache):
        os.remove(cache)


# ═══════════════════════════════════════════════════════════════════════════════
# SPOTIFY — CONEXIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def _intentar_conexion_spotify(client_id: str, client_secret: str) -> tuple[spotipy.Spotify | None, str | None]:
    """
    Intenta conectar con Spotify.
    Devuelve (sp, None) si tiene éxito, o (None, tipo_error).
    tipo_error puede ser:
      - 'premium_required': la cuenta del desarrollador no tiene Premium (HTTP 403).
      - 'invalid_credentials': id/secret incorrectos u otro error.
    """
    redirect_uri = "http://127.0.0.1:8888/callback"
    cache_path = os.path.join(_dir_script(), ".cache")
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="playlist-read-private playlist-read-collaborative",
            cache_path=cache_path,
        ))
        sp.current_user()
        return sp, None
    except spotipy.exceptions.SpotifyException as e:
        msg = str(e).lower()
        if e.http_status == 403 or "premium" in msg:
            return None, "premium_required"
        return None, "invalid_credentials"
    except Exception as e:
        msg = str(e).lower()
        if "premium" in msg or "403" in msg:
            return None, "premium_required"
        return None, "invalid_credentials"


def conectar_spotify() -> spotipy.Spotify | None:
    """
    Conecta con Spotify.
    Si las credenciales son válidas pero falla por requerimiento de Premium (403),
    guarda las credenciales y devuelve None para pasar automáticamente a modo CSV/alternativo.
    """
    # 1) Intentar credenciales guardadas
    creds = cargar_credenciales()
    if creds:
        print("   Usando credenciales guardadas...")
        sp, error = _intentar_conexion_spotify(creds["client_id"], creds["client_secret"])
        if sp:
            return sp
        if error == "premium_required":
            print("\n   ⚠  Spotify Web API requiere cuenta Spotify Premium para el desarrollador de la app.")
            print("      Tus credenciales (Client ID / Secret) son correctas, pero Spotify bloquea el acceso")
            print("      directo a la API si la cuenta de Spotify es Free (Error 403 Forbidden).")
            return None
        print("   ⚠  Las credenciales guardadas ya no son válidas.")
        borrar_cache_spotify()

    # 2) Intentar variables de entorno
    env_id = os.environ.get("SPOTIPY_CLIENT_ID")
    env_secret = os.environ.get("SPOTIPY_CLIENT_SECRET")
    if env_id and env_secret:
        print("   Usando variables de entorno...")
        sp, error = _intentar_conexion_spotify(env_id, env_secret)
        if sp:
            guardar_credenciales(env_id, env_secret)
            return sp
        if error == "premium_required":
            guardar_credenciales(env_id, env_secret)
            print("\n   ⚠  Spotify Web API requiere cuenta Spotify Premium para el desarrollador de la app.")
            print("      Tus credenciales son correctas, pero Spotify bloquea la API para cuentas Free.")
            return None
        print("   ⚠  Las credenciales de las variables de entorno no son válidas.")
        borrar_cache_spotify()

    # 3) Solicitar al usuario (con reintentos)
    for intento in range(3):
        client_id, client_secret = solicitar_credenciales()
        borrar_cache_spotify()
        sp, error = _intentar_conexion_spotify(client_id, client_secret)
        if sp:
            guardar_credenciales(client_id, client_secret)
            return sp
        if error == "premium_required":
            guardar_credenciales(client_id, client_secret)
            print("\n   ✅ Credenciales verificadas y guardadas.")
            print("   ⚠  Sin embargo, Spotify rechaza las peticiones (HTTP 403):")
            print("      'Active premium subscription required for the owner of the app'.")
            print("      Spotify exige cuenta Premium al creador de la App para usar su API.")
            return None
        print("   ❌ Credenciales no válidas. Verifica el Client ID y el Client Secret.")

    print("   ❌ No se pudo conectar a la API de Spotify.")
    return None


def obtener_playlists_spotify(sp: spotipy.Spotify) -> list[dict]:
    """Obtiene todas las playlists del usuario de Spotify."""
    playlists = []
    resultados = sp.current_user_playlists(limit=50)
    while resultados:
        for pl in resultados["items"]:
            playlists.append({
                "id": pl["id"],
                "nombre": pl["name"],
                "total": pl["tracks"]["total"],
                "propietario": pl["owner"]["display_name"],
            })
        if resultados["next"]:
            resultados = sp.next(resultados)
        else:
            break
    return playlists


def obtener_canciones_spotify(sp: spotipy.Spotify, playlist_id: str) -> list[dict]:
    """
    Obtiene todas las canciones de una playlist de Spotify.

    NOTA: Desde 2024, la API de Spotify solo devuelve las canciones
    de playlists que el usuario autenticado posee o en las que colabora.
    Para playlists ajenas solo se devuelven los metadatos (sin canciones).
    """
    canciones = []
    try:
        resultados = sp.playlist_tracks(
            playlist_id,
            fields="items(track(name,artists(name))),next",
        )
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 404:
            print("   ❌ No se puede acceder a esta playlist.")
            print("      Solo puedes leer playlists propias o en las que colaboras.")
            return canciones
        raise

    while resultados:
        items = resultados.get("items", [])
        if not items and not canciones:
            print("   ⚠  No se obtuvieron canciones. Puede que la playlist no sea tuya.")
            print("      La API de Spotify solo permite leer playlists propias o colaborativas.")
            break
        for item in items:
            track = item.get("track")
            if track and track.get("name"):
                artistas = [a["name"] for a in track.get("artists", [])]
                canciones.append({"titulo": track["name"], "artistas": artistas})
        if resultados.get("next"):
            resultados = sp.next(resultados)
        else:
            break
    return canciones


def seleccionar_playlist_spotify(sp: spotipy.Spotify) -> tuple[str, str, list[dict]]:
    """Muestra las playlists de Spotify y permite al usuario seleccionar una."""
    print("\n🎵 Obteniendo tus playlists de Spotify...\n")
    playlists = obtener_playlists_spotify(sp)

    if not playlists:
        sys.exit("No se encontraron playlists en tu cuenta de Spotify.")

    print(f"{'#':>4}  {'Playlist':<50} {'Canciones':>10}  {'Propietario'}")
    print("─" * 85)
    for i, pl in enumerate(playlists, 1):
        print(f"{i:>4}  {pl['nombre']:<50} {pl['total']:>10}  {pl['propietario']}")

    print()
    while True:
        try:
            opcion = input("Selecciona el número de la playlist a transferir (0 para cancelar): ").strip()
            num = int(opcion)
            if num == 0:
                sys.exit("Operación cancelada.")
            if 1 <= num <= len(playlists):
                seleccionada = playlists[num - 1]
                print(f'\n✅ Seleccionada: "{seleccionada["nombre"]}" ({seleccionada["total"]} canciones)')
                canciones = obtener_canciones_spotify(sp, seleccionada["id"])
                return seleccionada["id"], seleccionada["nombre"], canciones
            else:
                print(f"  ⚠  Introduce un número entre 1 y {len(playlists)}")
        except ValueError:
            print("  ⚠  Introduce un número válido.")


def leer_spotify_csv(ruta_csv: str) -> list[dict]:
    """Lee un CSV exportado de Spotify (compatible con Exportify, Soundiiz, TuneMyMusic, Spotlistr)."""
    if not os.path.exists(ruta_csv):
        print(f"   ❌ No se encuentra el archivo CSV en: {ruta_csv}")
        return []

    pistas = []
    with open(ruta_csv, "r", encoding="utf-8-sig") as f:
        lector = csv.DictReader(f)
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
                pistas.append({"titulo": titulo.strip(), "artistas": artistas})

    return pistas


def obtener_canciones_por_url(url_o_id: str) -> tuple[str, list[dict]]:
    """
    Extrae el nombre y todas las canciones de una playlist de Spotify
    a partir de su enlace (ej: https://open.spotify.com/playlist/...) o ID.
    NO requiere cuenta Premium ni credenciales de API.
    """
    if not HAS_SCRAPER:
        print("   ❌ La librería 'spotifyscraper' no está instalada.")
        print("      Instálala con: pip install spotifyscraper")
        return "", []

    url_limpia = url_o_id.strip().split("?")[0]
    print(f"\n🔍 Extrayendo canciones directamente de Spotify ({url_limpia})...")
    try:
        with SpotifyClient() as client:
            # max_tracks=None asegura que se descarguen TODAS las canciones sin el tope de 100
            playlist = client.get_playlist(url_limpia, max_tracks=None)
            nombre = playlist.name
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
    except Exception as e:
        print(f"   ❌ Error al extraer la playlist: {e}")
        return "", []


def obtener_playlists_usuario_publicas(usuario: str) -> list[dict]:
    """
    Obtiene las listas públicas de un usuario de Spotify a partir de su nombre de usuario,
    enlace de perfil (open.spotify.com/user/...) o ID.
    NO requiere cuenta Premium ni credenciales de API.
    """
    user_id = usuario.strip().strip('"').strip()
    if "spotify.com/user/" in user_id:
        user_id = user_id.split("spotify.com/user/")[1].split("?")[0].strip("/")
    elif "?" in user_id:
        user_id = user_id.split("?")[0].strip("/")

    print(f"\n🔍 Buscando playlists públicas del usuario '{user_id}'...")
    encontradas = []
    vistos_ids = set()

    # Estrategia 1: Parsear initialState en el HTML del perfil público
    try:
        url_perfil = f"https://open.spotify.com/user/{urllib.parse.quote(user_id)}"
        req = urllib.request.Request(url_perfil, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

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

    # Si encontramos las listas directamente en su perfil, obtenemos sus canciones completas
    if encontradas and HAS_SCRAPER:
        playlists_detalles = []
        try:
            with SpotifyClient() as client:
                for item in encontradas[:30]:
                    try:
                        # max_tracks=None para obtener el conteo total real de canciones
                        pl = client.get_playlist(item["url"], max_tracks=None)
                        playlists_detalles.append({
                            "id": item["id"],
                            "nombre": pl.name,
                            "total": len(getattr(pl, "tracks", [])),
                            "url": item["url"],
                        })
                    except Exception:
                        playlists_detalles.append(item)
            return playlists_detalles
        except Exception:
            return encontradas

    return encontradas


def seleccionar_playlist_alternativa() -> tuple[str, list[dict]]:
    """
    Permite al usuario transferir una playlist sin necesitar cuenta Premium:
      Opción 1: Pegar el enlace directo de la playlist (URL)
      Opción 2: Buscar por nombre de usuario de Spotify y elegir una de sus listas públicas
      Opción 3: Cargar un archivo CSV (Exportify / Soundiiz / etc.)
    """
    print("\n" + "─" * 70)
    print("  🎵 MODO SIN SPOTIFY PREMIUM (Extracción directa)")
    print("─" * 70)
    print("  Opciones disponibles para transferir:")
    print("    1) Pegar el enlace/URL de la playlist")
    print("    2) Buscar por nombre de usuario de Spotify y elegir entre sus listas")
    print("    3) Usar un archivo CSV existente (Exportify / Soundiiz)")
    print("─" * 70)

    while True:
        eleccion = input("\nElige una opción (1: Enlace URL / 2: Por Usuario / 3: Archivo CSV): ").strip()

        # ── Opción 1: Enlace directo ──
        if eleccion in ("1", "url", "enlace", ""):
            print("\n💡 Para copiar el enlace en Spotify:")
            print("   En Spotify: clic derecho en la playlist → Compartir → Copiar enlace a la playlist")
            url = input("\nPega el enlace de la playlist de Spotify: ").strip().strip('"')
            if not url:
                print("  ⚠ No se introdujo ningún enlace.")
                continue

            nombre, canciones = obtener_canciones_por_url(url)
            if canciones:
                print(f'\n✅ Extraídas {len(canciones)} canciones de la playlist "{nombre}".')
                nombre_custom = input(f'Nombre para la lista en YouTube Music [{nombre}]: ').strip()
                return (nombre_custom if nombre_custom else nombre), canciones
            else:
                print("  ⚠ No se pudieron extraer canciones con ese enlace.")
                reintentar = input("  ¿Deseas intentar de nuevo? (s/n): ").strip().lower()
                if reintentar not in ("s", "si", "sí", "y"):
                    continue

        # ── Opción 2: Por nombre de usuario ──
        elif eleccion in ("2", "usuario", "user"):
            usuario = input("\nIntroduce el nombre de usuario o enlace de perfil de Spotify: ").strip()
            if not usuario:
                print("  ⚠ Nombre de usuario vacío.")
                continue

            usuario_limpio = usuario.strip().strip('"').strip()
            if "spotify.com/user/" in usuario_limpio:
                usuario_limpio = usuario_limpio.split("spotify.com/user/")[1].split("?")[0].strip("/")

            playlists = obtener_playlists_usuario_publicas(usuario)
            if not playlists:
                print(f"  ❌ No se encontraron playlists públicas para '{usuario_limpio}'.")
                print("     Verifica que el usuario tenga listas públicas o usa la opción 1 (Enlace directo).")
                continue

            print(f"\n📋 Playlists públicas de '{usuario_limpio}':")
            print(f"{'#':>4}  {'Playlist':<50} {'Canciones':>10}")
            print("─" * 68)
            for i, pl in enumerate(playlists, 1):
                print(f"{i:>4}  {pl['nombre']:<50} {str(pl['total']):>10}")

            while True:
                sel = input("\nElige el número de la lista a transferir (0 para volver): ").strip()
                if sel == "0":
                    break
                if sel.isdigit() and 1 <= int(sel) <= len(playlists):
                    elegida = playlists[int(sel) - 1]
                    nombre, canciones = obtener_canciones_por_url(elegida["url"])
                    if canciones:
                        print(f'\n✅ Extraídas {len(canciones)} canciones de la playlist "{nombre}".')
                        nombre_custom = input(f'Nombre para la lista en YouTube Music [{nombre}]: ').strip()
                        return (nombre_custom if nombre_custom else nombre), canciones
                    else:
                        print("  ⚠ No se pudieron extraer canciones de esa playlist.")
                        break
                else:
                    print(f"  ⚠ Introduce un número entre 1 y {len(playlists)}.")

        # ── Opción 3: Archivo CSV ──
        elif eleccion in ("3", "csv"):
            archivos_csv = [f for f in os.listdir(_dir_script()) if f.lower().endswith(".csv") and not f.startswith("solo_") and not f.startswith("no_encontradas")]

            if archivos_csv:
                print("\nArchivos CSV detectados en la carpeta:")
                for i, nombre in enumerate(archivos_csv, 1):
                    print(f"  {i}) {nombre}")
                print("  0) Escribir ruta manualmente")

                opcion = input("\nElige una opción (número o ruta): ").strip()
                if opcion.isdigit():
                    idx = int(opcion)
                    if idx == 0:
                        ruta = input("Introduce la ruta completa o nombre del archivo CSV: ").strip().strip('"')
                    elif 1 <= idx <= len(archivos_csv):
                        ruta = os.path.join(_dir_script(), archivos_csv[idx - 1])
                    else:
                        ruta = opcion
                else:
                    ruta = opcion.strip('"')
            else:
                ruta = input("Introduce la ruta o nombre del archivo CSV (ej: espanola.csv): ").strip().strip('"')

            if not os.path.isabs(ruta):
                ruta = os.path.join(_dir_script(), ruta)

            pistas = leer_spotify_csv(ruta)
            if pistas:
                nombre_base = os.path.splitext(os.path.basename(ruta))[0]
                nombre_personalizado = input(f'Nombre para la playlist en YouTube Music [{nombre_base}]: ').strip()
                nombre_final = nombre_personalizado if nombre_personalizado else nombre_base
                return nombre_final, pistas
            else:
                print("  ⚠ No se pudieron cargar canciones de ese archivo CSV.")

    sys.exit("Operación cancelada.")

def conectar_ytm(auth_file: str) -> YTMusic:
    """Conecta con YouTube Music."""
    if not os.path.exists(auth_file):
        sys.exit(
            f"❌ No se encuentra el archivo de autenticación: {auth_file}\n"
            "   Consulta el manual de instalación para generarlo."
        )
    return YTMusic(auth_file)


def buscar_listas_ytm(yt: YTMusic, nombre_base: str) -> list[dict]:
    """
    Busca en YTM todas las listas que coincidan con el nombre base.
    Devuelve listas como "MiLista", "MiLista 2", "MiLista 3", etc.
    """
    todas = yt.get_library_playlists(limit=None)
    patron = re.compile(rf"^{re.escape(nombre_base)}(\s+\d+)?$")
    encontradas = []
    for pl in todas:
        if patron.match(pl["title"]):
            encontradas.append(pl)
    # Ordenar: primero la original, luego por número
    def orden(p):
        m = re.search(r"\s+(\d+)$", p["title"])
        return int(m.group(1)) if m else 0
    encontradas.sort(key=orden)
    return encontradas


def obtener_canciones_ytm(yt: YTMusic, playlists: list[dict]) -> list[dict]:
    """Obtiene todas las canciones de una o varias playlists de YTM."""
    canciones = []
    for pl in playlists:
        print(f'  📋 Leyendo "{pl["title"]}" de YouTube Music...')
        datos = yt.get_playlist(pl["playlistId"], limit=None)
        for t in datos.get("tracks", []):
            canciones.append({
                "id": t.get("videoId"),
                "titulo": t["title"],
                "artistas": [a["name"] for a in (t.get("artists") or [])],
            })
    return canciones


def buscar_en_ytm(yt: YTMusic, cancion: dict) -> str | None:
    """
    Busca una canción en YouTube Music y devuelve su videoId si la encuentra.
    Utiliza búsqueda multietapa y fallback a vídeos:
      1. Búsqueda con título completo y artista (filtro songs)
      2. Búsqueda sin signos de interrogación/admiración y título base (filtro songs)
      3. Fallback en filtro videos (para canciones indie subidas como videoclip oficial)
    """
    artista = cancion["artistas"][0] if cancion["artistas"] else ""
    k = clave(cancion["titulo"], cancion["artistas"])
    tit_original = cancion["titulo"]

    consultas = [
        f"{tit_original} {artista}".strip(),
    ]
    # Variante sin signos ¿ ? ¡ !
    sin_signos = re.sub(r"[¿?¡!]+", " ", tit_original).strip()
    if sin_signos != tit_original:
        consultas.append(f"{sin_signos} {artista}".strip())

    # Variante con título base normalizado
    base_tit = normalizar(tit_original)
    if base_tit and base_tit.lower() != tit_original.lower():
        consultas.append(f"{base_tit} {artista}".strip())

    # Eliminar duplicados en las consultas
    consultas = list(dict.fromkeys(c for c in consultas if c))

    # Fase 1: Intentar en catálogo oficial de canciones ('songs')
    for query in consultas:
        try:
            resultados = yt.search(query, filter="songs", limit=7)
            for r in resultados:
                artistas_r = [a["name"] for a in r.get("artists", []) if isinstance(a, dict)]
                if coincide(k, clave(r["title"], artistas_r), raw_a=tit_original, raw_b=r["title"]):
                    return r["videoId"]
        except Exception:
            pass

    # Fase 2: Si no está en 'songs', buscar en 'videos' (muchas canciones indie están catalogadas como videoclip)
    for query in consultas:
        try:
            resultados = yt.search(query, filter="videos", limit=7)
            for r in resultados:
                artistas_r = [a["name"] for a in r.get("artists", []) if isinstance(a, dict)]
                if coincide(k, clave(r["title"], artistas_r), raw_a=tit_original, raw_b=r["title"]):
                    return r["videoId"]
        except Exception:
            pass

    return None


def calcular_nombre_lista(nombre_base: str, indice: int) -> str:
    """Genera el nombre de lista: 'MiLista', 'MiLista 2', 'MiLista 3'..."""
    if indice <= 1:
        return nombre_base
    return f"{nombre_base} {indice}"


def obtener_capacidad_listas(yt: YTMusic, listas_existentes: list[dict]) -> list[dict]:
    """
    Devuelve la información de cada lista con su capacidad restante.
    """
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


def añadir_canciones_ytm(
    yt: YTMusic,
    nombre_base: str,
    video_ids: list[str],
    listas_existentes: list[dict],
) -> None:
    """
    Añade canciones a las listas de YTM, creando nuevas si es necesario.
    Respeta el límite de 5000 canciones por lista.
    Envía las canciones en lotes para evitar errores de payload.
    """
    if not video_ids:
        print("  ℹ  No hay canciones que añadir.")
        return

    # Obtener información de capacidad de las listas existentes
    if listas_existentes:
        info_listas = obtener_capacidad_listas(yt, listas_existentes)
    else:
        info_listas = []

    ids_pendientes = list(video_ids)
    listas_creadas = []

    # Primero, intentar llenar las listas existentes que tengan espacio
    for lista in info_listas:
        if not ids_pendientes:
            break
        if lista["espacio_libre"] > 0:
            lote_total = ids_pendientes[:lista["espacio_libre"]]
            ids_pendientes = ids_pendientes[lista["espacio_libre"]:]
            print(f'  ➕ Añadiendo {len(lote_total)} canciones a "{lista["title"]}"...')
            # Enviar en lotes pequeños para evitar errores de payload.
            # Usamos duplicates=True porque con False, si hay UN duplicado,
            # se rechaza TODO el lote.
            for lote in en_lotes(lote_total):
                yt.add_playlist_items(lista["playlistId"], videoIds=lote, duplicates=True)
                time.sleep(PAUSA_BUSQUEDA)
            print(f'  ✅ Añadidas {len(lote_total)} canciones a "{lista["title"]}"')

    # Si quedan canciones, crear nuevas listas
    if ids_pendientes:
        # Determinar el siguiente número consecutivo
        if listas_existentes:
            numeros = []
            for pl in listas_existentes:
                m = re.search(r"\s+(\d+)$", pl["title"])
                numeros.append(int(m.group(1)) if m else 1)
            siguiente = max(numeros) + 1
        else:
            siguiente = 1  # Primera lista, sin número

        while ids_pendientes:
            nombre_nueva = calcular_nombre_lista(nombre_base, siguiente)
            lote_total = ids_pendientes[:MAX_CANCIONES_LISTA_YTM]
            ids_pendientes = ids_pendientes[MAX_CANCIONES_LISTA_YTM:]

            print(f'  🆕 Creando lista "{nombre_nueva}" con {len(lote_total)} canciones...')
            # Crear la lista vacía y añadir canciones en lotes
            primer_lote = lote_total[:LOTE_API]
            pl_id = yt.create_playlist(
                title=nombre_nueva,
                description=f"Transferida desde Spotify — {nombre_base}",
                video_ids=primer_lote,
            )
            # Añadir el resto en lotes
            for lote in en_lotes(lote_total[LOTE_API:]):
                yt.add_playlist_items(pl_id, videoIds=lote, duplicates=True)
                time.sleep(PAUSA_BUSQUEDA)
            listas_creadas.append(nombre_nueva)
            print(f'  ✅ Lista "{nombre_nueva}" creada con {len(lote_total)} canciones.')
            siguiente += 1

    if listas_creadas:
        print(f"\n  📝 Listas nuevas creadas: {', '.join(listas_creadas)}")
        if len(listas_creadas) + len(listas_existentes) > 1:
            print(
                "  💡 Consejo: Puedes combinar manualmente todas las listas parciales "
                "en una sola desde la app de YouTube Music."
            )


# ═══════════════════════════════════════════════════════════════════════════════
# INFORMES
# ═══════════════════════════════════════════════════════════════════════════════

def guardar_csv(ruta: str, filas: list[dict]) -> None:
    """Guarda una lista de canciones en un archivo CSV."""
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["titulo", "artistas"])
        for t in filas:
            w.writerow([t["titulo"], ", ".join(t["artistas"])])


def diferencia(origen: list[dict], destino: list[dict]) -> list[dict]:
    """Devuelve las canciones de 'origen' que no están en 'destino'."""
    claves_destino = [clave(t["titulo"], t["artistas"]) for t in destino]
    faltan = []
    for t in origen:
        k = clave(t["titulo"], t["artistas"])
        if not any(coincide(k, c) for c in claves_destino):
            faltan.append(t)
    return faltan


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 70)
    print("  🎶  SPOTIFY → YOUTUBE MUSIC — Transferencia de Playlists  🎶")
    print("=" * 70)

    # ── Determinar archivo de autenticación YTM ──
    auth_file = "oauth.json"
    if not os.path.exists(auth_file):
        auth_file = "headers_auth.json"

    # Permitir sobrescribir por variable de entorno
    auth_file = os.environ.get("YTM_AUTH_FILE", auth_file)

    # ── Conectar con Spotify ──
    print("\n🔗 Conectando con Spotify...")
    sp = conectar_spotify()
    
    if sp:
        try:
            usuario_sp = sp.current_user()
            tipo_cuenta = usuario_sp.get("product", "free")
            print(f"   Conectado como: {usuario_sp['display_name']} ({tipo_cuenta})")
            if tipo_cuenta == "free":
                print("   ℹ  Cuenta gratuita detectada. La lectura de playlists propias funciona igual.")
            print("   ⚠  Recuerda: solo se pueden leer playlists propias o colaborativas.")
            
            # Seleccionar playlist directamente desde la API
            playlist_id, nombre_playlist, canciones_sp = seleccionar_playlist_spotify(sp)
        except Exception as e:
            print(f"   ⚠ Error al consultar la API de Spotify: {e}")
            print("   Cambiando a modo archivo CSV...")
            sp = None

    if not sp:
        # Modo fallback para cuentas gratuitas sin Developer Premium
        nombre_playlist, canciones_sp = seleccionar_playlist_alternativa()

    if not canciones_sp:
        sys.exit(
            "\n❌ No se obtuvieron canciones para transferir.\n"
            "   Comprueba la playlist o el archivo CSV e inténtalo de nuevo."
        )

    # ── Conectar con YouTube Music ──
    print("\n🔗 Conectando con YouTube Music...")
    yt = conectar_ytm(auth_file)
    print("   Conexión establecida.")

    # ── Buscar listas con el mismo nombre en YTM ──
    print(f'\n🔍 Buscando listas "{nombre_playlist}" en YouTube Music...')
    listas_ytm = buscar_listas_ytm(yt, nombre_playlist)

    if listas_ytm:
        nombres = [pl["title"] for pl in listas_ytm]
        print(f"   Encontradas: {', '.join(nombres)}")

        # Obtener canciones de todas las listas YTM existentes
        canciones_ytm = obtener_canciones_ytm(yt, listas_ytm)
        print(f"   Total de canciones en YTM: {len(canciones_ytm)}")

        # Calcular diferencias
        solo_sp = diferencia(canciones_sp, canciones_ytm)
        solo_ytm = diferencia(canciones_ytm, canciones_sp)

        print(f"\n📋 Resultado de la comparación:")
        print(f"   ▸ Canciones en común: ~{len(canciones_sp) - len(solo_sp)}")
        print(f"   ▸ Solo en Spotify (faltan en YTM): {len(solo_sp)}")
        print(f"   ▸ Solo en YTM (no están en Spotify): {len(solo_ytm)}")

        # Guardar informes
        if solo_sp:
            guardar_csv("solo_en_spotify.csv", solo_sp)
            print("   📄 Informe guardado: solo_en_spotify.csv")
        if solo_ytm:
            guardar_csv("solo_en_youtube_music.csv", solo_ytm)
            print("   📄 Informe guardado: solo_en_youtube_music.csv")

        if not solo_sp:
            print("\n✅ ¡La lista de YouTube Music ya está completa! No faltan canciones.")
            return

        canciones_a_buscar = solo_sp
    else:
        print("   No se encontró ninguna lista con ese nombre en YTM.")
        print("   Se creará una nueva.")
        canciones_a_buscar = canciones_sp

    # ── Confirmación del usuario ──
    print(f"\n🔄 Se van a buscar {len(canciones_a_buscar)} canciones en YouTube Music.")
    respuesta = input("   ¿Deseas continuar? (s/N): ").strip().lower()
    if respuesta not in ("s", "si", "sí", "y", "yes"):
        print("   Operación cancelada.")
        return

    # ── Buscar canciones en YTM ──
    print(f"\n🔎 Buscando {len(canciones_a_buscar)} canciones en YouTube Music...")
    video_ids = []
    no_encontradas = []

    for i, cancion in enumerate(canciones_a_buscar, 1):
        artista_str = cancion["artistas"][0] if cancion["artistas"] else "?"
        progreso = f"[{i}/{len(canciones_a_buscar)}]"

        vid = buscar_en_ytm(yt, cancion)
        if vid:
            video_ids.append(vid)
            print(f"   {progreso} ✅ {cancion['titulo']} — {artista_str}")
        else:
            no_encontradas.append(cancion)
            print(f"   {progreso} ❌ {cancion['titulo']} — {artista_str}")

        time.sleep(PAUSA_BUSQUEDA)

    # Eliminar duplicados conservando el orden
    video_ids = list(dict.fromkeys(video_ids))

    print(f"\n📊 Resumen de búsqueda:")
    print(f"   ▸ Encontradas: {len(video_ids)}")
    print(f"   ▸ No encontradas: {len(no_encontradas)}")

    if no_encontradas:
        guardar_csv("no_encontradas_en_ytm.csv", no_encontradas)
        print("   📄 Canciones no encontradas guardadas en: no_encontradas_en_ytm.csv")

    if not video_ids:
        print("\n⚠  No se encontró ninguna canción coincidente en YouTube Music.")
        return

    # ── Añadir canciones a YTM ──
    print(f"\n📥 Añadiendo {len(video_ids)} canciones a YouTube Music...")
    añadir_canciones_ytm(yt, nombre_playlist, video_ids, listas_ytm)

    print("\n" + "=" * 70)
    print("  🎉  ¡Transferencia completada!  🎉")
    print("=" * 70)


if __name__ == "__main__":
    main()
