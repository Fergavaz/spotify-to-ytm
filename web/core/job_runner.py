"""
Gestor de tareas en segundo plano (Background Job Manager).
Permite ejecutar transferencias asíncronas con seguimiento de progreso,
registro de logs en tiempo real y generación de informes CSV.
"""

import csv
import io
import os
import threading
import time
import uuid
from typing import Dict, Any, List
from core.ytm_engine import (
    obtener_cliente_ytm,
    buscar_listas_ytm,
    obtener_canciones_ytm,
    buscar_en_ytm,
    diferencia_canciones,
    anadir_canciones_ytm,
    PAUSA_BUSQUEDA,
)

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def crear_tarea(nombre_playlist: str, canciones: List[dict], modo_sincronizar: bool, ruta_auth: str, dir_reportes: str) -> str:
    """Crea una nueva tarea y lanza el hilo en segundo plano."""
    job_id = str(uuid.uuid4())[:8]
    job_data = {
        "id": job_id,
        "nombre_playlist": nombre_playlist,
        "total_canciones": len(canciones),
        "procesadas": 0,
        "anadidas": 0,
        "existentes": 0,
        "no_encontradas_count": 0,
        "progreso_porcentaje": 0,
        "estado": "en_cola",  # en_cola, ejecutando, completado, error
        "mensaje": "Iniciando transferencia...",
        "logs": [],
        "listas_afectadas": [],
        "canciones_no_encontradas": [],
        "solo_en_spotify": [],
        "solo_en_ytm": [],
        "error": None,
        "inicio": time.time(),
        "fin": None,
    }

    with JOBS_LOCK:
        JOBS[job_id] = job_data

    thread = threading.Thread(
        target=_ejecutar_transferencia,
        args=(job_id, nombre_playlist, canciones, modo_sincronizar, ruta_auth, dir_reportes),
        daemon=True,
    )
    thread.start()
    return job_id


def obtener_estado_tarea(job_id: str) -> Dict[str, Any] | None:
    """Devuelve los datos actuales del estado de la tarea."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        # Devolver una copia segura
        return {
            "id": job["id"],
            "nombre_playlist": job["nombre_playlist"],
            "total_canciones": job["total_canciones"],
            "procesadas": job["procesadas"],
            "anadidas": job["anadidas"],
            "existentes": job["existentes"],
            "no_encontradas_count": job["no_encontradas_count"],
            "progreso_porcentaje": job["progreso_porcentaje"],
            "estado": job["estado"],
            "mensaje": job["mensaje"],
            "logs": job["logs"][-60:],  # Últimos 60 logs
            "listas_afectadas": job["listas_afectadas"],
            "error": job["error"],
            "ha_finalizado": job["estado"] in ("completado", "error"),
        }


def _agregar_log(job_id: str, texto: str, nivel: str = "info"):
    timestamp = time.strftime("%H:%M:%S")
    linea = f"[{timestamp}] {texto}"
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id]["logs"].append({"timestamp": timestamp, "texto": texto, "nivel": nivel})
            JOBS[job_id]["mensaje"] = texto


def _guardar_csv(ruta: str, canciones: List[dict]):
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["titulo", "artistas"])
            for t in canciones:
                w.writerow([t["titulo"], ", ".join(t.get("artistas", []))])
    except Exception:
        pass


def _ejecutar_transferencia(
    job_id: str,
    nombre_playlist: str,
    canciones: List[dict],
    modo_sincronizar: bool,
    ruta_auth: str,
    dir_reportes: str,
):
    try:
        with JOBS_LOCK:
            JOBS[job_id]["estado"] = "ejecutando"

        _agregar_log(job_id, f"Iniciando transferencia para '{nombre_playlist}' ({len(canciones)} pistas)")
        yt = obtener_cliente_ytm(ruta_auth)

        listas_existentes = []
        canciones_existentes_ytm = []
        canciones_a_buscar = canciones

        if modo_sincronizar:
            _agregar_log(job_id, f"Buscando listas previas de '{nombre_playlist}' en tu biblioteca de YouTube Music...")
            listas_existentes = buscar_listas_ytm(yt, nombre_playlist)
            if listas_existentes:
                nombres = ", ".join(f'"{p["title"]}"' for p in listas_existentes)
                _agregar_log(job_id, f"Listas existentes encontradas en YTM: {nombres}")
                canciones_existentes_ytm = obtener_canciones_ytm(
                    yt, listas_existentes, log_cb=lambda msg: _agregar_log(job_id, msg)
                )
                _agregar_log(job_id, f"Total en YTM actualmente: {len(canciones_existentes_ytm)} canciones.")

                # Calcular diferencias
                canciones_a_buscar = diferencia_canciones(canciones, canciones_existentes_ytm)
                existentes_count = len(canciones) - len(canciones_a_buscar)

                with JOBS_LOCK:
                    JOBS[job_id]["existentes"] = existentes_count
                    JOBS[job_id]["solo_en_spotify"] = canciones_a_buscar
                    JOBS[job_id]["solo_en_ytm"] = diferencia_canciones(canciones_existentes_ytm, canciones)

                _agregar_log(job_id, f"Canciones que ya estaban en YTM: {existentes_count}")
                _agregar_log(job_id, f"Canciones nuevas a transferir: {len(canciones_a_buscar)}")
            else:
                _agregar_log(job_id, "No existen listas previas con ese nombre en YTM. Se creará una nueva.")

        if not canciones_a_buscar:
            _agregar_log(job_id, "¡Tu lista de YouTube Music ya está completamente sincronizada! No hay nada que añadir.", "success")
            with JOBS_LOCK:
                JOBS[job_id]["estado"] = "completado"
                JOBS[job_id]["progreso_porcentaje"] = 100
                JOBS[job_id]["fin"] = time.time()
            return

        total_a_buscar = len(canciones_a_buscar)
        encontrados_ids = []
        no_encontradas = []

        _agregar_log(job_id, f"Buscando {total_a_buscar} canciones en YouTube Music...")

        for idx, t in enumerate(canciones_a_buscar, 1):
            artistas_str = ", ".join(t.get("artistas", []))
            tit = t.get("titulo", "")

            vid = buscar_en_ytm(yt, t)
            if vid:
                encontrados_ids.append(vid)
                _agregar_log(job_id, f"[{idx}/{total_a_buscar}] ✓ Encontrada: {tit} ({artistas_str})", "success")
            else:
                no_encontradas.append(t)
                _agregar_log(job_id, f"[{idx}/{total_a_buscar}] ✗ No encontrada: {tit} ({artistas_str})", "warning")

            # Actualizar progreso
            porcentaje = int((idx / total_a_buscar) * 85)  # Hasta el 85% para búsqueda, 15% restante para inserción
            with JOBS_LOCK:
                JOBS[job_id]["procesadas"] = idx
                JOBS[job_id]["no_encontradas_count"] = len(no_encontradas)
                JOBS[job_id]["progreso_porcentaje"] = porcentaje

            time.sleep(PAUSA_BUSQUEDA)

        with JOBS_LOCK:
            JOBS[job_id]["canciones_no_encontradas"] = no_encontradas

        # Guardar informes CSV en disco
        _guardar_csv(os.path.join(dir_reportes, f"{job_id}_no_encontradas.csv"), no_encontradas)
        with JOBS_LOCK:
            _guardar_csv(os.path.join(dir_reportes, f"{job_id}_solo_en_spotify.csv"), JOBS[job_id].get("solo_en_spotify", []))
            _guardar_csv(os.path.join(dir_reportes, f"{job_id}_solo_en_ytm.csv"), JOBS[job_id].get("solo_en_ytm", []))

        # Inserción en playlists de YTM
        if encontrados_ids:
            _agregar_log(job_id, f"Añadiendo {len(encontrados_ids)} canciones a YouTube Music...")
            listas_afectadas = anadir_canciones_ytm(
                yt,
                nombre_playlist,
                encontrados_ids,
                listas_existentes,
                log_cb=lambda msg: _agregar_log(job_id, msg),
            )
            with JOBS_LOCK:
                JOBS[job_id]["anadidas"] = len(encontrados_ids)
                JOBS[job_id]["listas_afectadas"] = listas_afectadas
        else:
            _agregar_log(job_id, "No se encontró ninguna de las canciones faltantes.", "warning")

        with JOBS_LOCK:
            JOBS[job_id]["progreso_porcentaje"] = 100
            JOBS[job_id]["estado"] = "completado"
            JOBS[job_id]["fin"] = time.time()

        _agregar_log(
            job_id,
            f"¡Transferencia finalizada! Añadidas: {len(encontrados_ids)}, "
            f"Existentes: {JOBS[job_id]['existentes']}, No encontradas: {len(no_encontradas)}",
            "success",
        )

    except Exception as e:
        _agregar_log(job_id, f"Error durante la transferencia: {str(e)}", "error")
        with JOBS_LOCK:
            JOBS[job_id]["estado"] = "error"
            JOBS[job_id]["error"] = str(e)
            JOBS[job_id]["fin"] = time.time()
