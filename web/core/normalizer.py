"""
Normalización de títulos y artistas para coincidencia flexible
entre canciones de Spotify y YouTube Music.
"""

import difflib
import re
import unicodedata

UMBRAL_SIMILITUD = 0.88


def limpiar_cadena(texto: str) -> str:
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
    return limpiar_cadena(t)


def normalizar_candidatos(texto: str) -> list[str]:
    """
    Genera candidatos de normalización para títulos complejos o formatos de vídeo
    (ej: 'Valiente Bosque - ¿A Dónde Vamos?' -> ['a donde vamos', 'valiente bosque'],
     o 'Suerte (Whenever, Wherever)' -> ['suerte', 'whenever wherever']).
    """
    cands = [limpiar_cadena(texto)]
    # Si tiene guión 'Artista - Cancion' o 'Cancion - Artista'
    if " - " in texto:
        partes = texto.split(" - ")
        for p in partes:
            n = limpiar_cadena(p)
            if n:
                cands.append(n)
    # Si tiene paréntesis con título bilingüe ej: 'Suerte (Whenever, Wherever)'
    m = re.search(r"^([^(]+)\s*\(([^)]+)\)", texto)
    if m:
        c1 = limpiar_cadena(m.group(1))
        c2 = limpiar_cadena(m.group(2))
        if c1:
            cands.append(c1)
        if c2:
            cands.append(c2)
    return list(dict.fromkeys(c for c in cands if c))


def clave(titulo: str, artistas: list[str]) -> tuple[str, str]:
    """Genera clave normalizada (titulo_base, primer_artista)."""
    primero = artistas[0] if artistas else ""
    return normalizar(titulo), limpiar_cadena(primero)


def canciones_coinciden(t_a: dict, t_b: dict) -> bool:
    """
    Compara dos diccionarios de canciones ({'titulo': ..., 'artistas': [...]})
    utilizando extracción multietapa de candidatos, coincidencias cruzadas entre todos los artistas
    y detección de formatos de YouTube (ej: 'Artista - Título (Letra)' con canal como artista).
    """
    tit_a_raw = t_a.get("titulo", "")
    tit_b_raw = t_b.get("titulo", "")
    arts_a = [limpiar_cadena(a) for a in t_a.get("artistas", []) if a]
    arts_b = [limpiar_cadena(a) for a in t_b.get("artistas", []) if a]

    cands_a = normalizar_candidatos(tit_a_raw)
    cands_b = normalizar_candidatos(tit_b_raw)

    # 1. Comprobar si los títulos coinciden
    tit_match = False
    for ca in cands_a:
        for cb in cands_b:
            if ca == cb:
                tit_match = True
                break
            sim = difflib.SequenceMatcher(None, ca, cb).ratio()
            if sim >= 0.82 or (len(ca) >= 4 and ca in cb) or (len(cb) >= 4 and cb in ca):
                tit_match = True
                break
        if tit_match:
            break

    if not tit_match:
        return False

    # 2. Comprobar artistas:
    if not arts_a or not arts_b:
        return True

    # a) ¿Coincide algún artista de A con algún artista de B?
    for a in arts_a:
        for b in arts_b:
            if a == b:
                return True
            sim = difflib.SequenceMatcher(None, a, b).ratio()
            if sim >= 0.80 or (len(a) >= 4 and a in b) or (len(b) >= 4 and b in a):
                return True

    # b) ¿El artista de A está dentro del título de B o viceversa?
    tit_a_limpio = limpiar_cadena(tit_a_raw)
    tit_b_limpio = limpiar_cadena(tit_b_raw)

    for a in arts_a:
        if len(a) >= 4 and a in tit_b_limpio:
            return True
    for b in arts_b:
        if len(b) >= 4 and b in tit_a_limpio:
            return True

    return False


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
        or (raw_b and len(a[1]) >= 4 and a[1] in limpiar_cadena(raw_b))
        or (raw_a and len(b[1]) >= 4 and b[1] in limpiar_cadena(raw_a))
    )
    return art_ok
