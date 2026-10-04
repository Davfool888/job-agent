"""Busqueda automatica y continua de vacantes.

Cada perfil activo se ejecuta segun su frecuencia (defecto 10 min).
Corre en el backend (nube), nunca en el navegador: con el PC apagado
las busquedas continuan mientras el backend este disponible.

Diseno anti-solapamiento:
- Lock en memoria (un solo proceso).
- Guardia persistida: un perfil con last_run_status == "running" y
  last_run_at reciente (< 30 min) se omite; tras 30 min se reintenta.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from datetime import timedelta

logger = logging.getLogger(__name__)

# Si una ejecucion murio hace mas de esto, se considera liberado el lock.
STALE_RUNNING_MINUTES = 30
# Maximo de queries por perfil y ejecucion (titulo + keywords).
MAX_QUERIES_PER_RUN = 10

_lock = threading.Lock()
_running_profiles: set[str] = set()
_scheduler = None
_last_tick: dict = {"at": None, "profiles": 0, "new": 0, "error": None}


def _new_db():
    """Sesion/handle fresca para el scheduler (fuera de requests)."""
    from app.config import DB_BACKEND

    if DB_BACKEND == "firestore":
        from app.database.firestore_client import FirestoreDatabase

        return FirestoreDatabase(), False
    from app.database.connection import SessionLocal

    return SessionLocal(), True


def _close_db(db, needs_close: bool) -> None:
    if needs_close:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass


def _profile_is_locked(profile: dict, now: datetime) -> bool:
    if str(profile.get("id")) in _running_profiles:
        return True
    if profile.get("last_run_status") == "running":
        last = profile.get("last_run_at")
        if last:
            try:
                started = datetime.fromisoformat(str(last))
                if now - started < timedelta(minutes=STALE_RUNNING_MINUTES):
                    return True
            except ValueError:
                pass
    return False


def build_queries(profile: dict) -> list[str]:
    """Titulo + palabras relacionadas, sin duplicados."""
    queries = []
    for query in [profile.get("title"), *(profile.get("keywords") or [])]:
        text = str(query or "").strip()
        if text and text.lower() not in {q.lower() for q in queries}:
            queries.append(text)
    return queries[:MAX_QUERIES_PER_RUN]


def run_profile(profile_id, *, db=None, uid: str | None = None, email: str | None = None) -> dict:
    """Ejecuta un perfil: scraping + dedup + analisis. Devuelve resumen."""
    from app.services import job_service as jobs
    from app.services import search_orchestrator as orch
    from app.services import search_profiles as profiles

    owns_db = db is None
    if owns_db:
        db, needs_close = _new_db()
    else:
        needs_close = False
    started_at = datetime.utcnow()
    summary = {
        "profile_id": str(profile_id), "found": 0, "new": 0,
        "analyzed": 0, "relevant": 0, "errors": [],
    }
    try:
        profile = profiles.get_profile(db, profile_id)
        if not profile:
            summary["errors"].append("perfil no existe")
            return summary
        if not profile.get("active"):
            summary["errors"].append("perfil inactivo")
            return summary
        if _profile_is_locked(profile, started_at):
            summary["errors"].append("ejecucion en curso (omitido)")
            return summary

        _running_profiles.add(str(profile_id))
        try:
            profiles.touch_run(
                db, profile_id, status="running", now=started_at
            )
            user_profile = jobs.get_profile(db, uid=uid, email=email)
            queries = build_queries(profile)
            sources = profile.get("sources") or ["computrabajo"]
            location = profile.get("location")
            max_age_days = int(profile.get("max_age_days") or 0)
            all_rows: list = []

            for source in sources:
                try:
                    scraper = orch.resolve_scraper(source)
                except ValueError as error:
                    summary["errors"].append(f"{source}: {error}")
                    continue
                rows: list = []
                for query in queries:
                    try:
                        found = orch.scrape_with(
                            scraper, source, query, max_pages=1,
                            location=location,
                        )
                    except Exception as error:  # noqa: BLE001
                        summary["errors"].append(
                            f"{source}/{query}: {str(error)[:150]}"
                        )
                        logger.warning(
                            "Scheduler %s/%s fallo: %s",
                            source, query, error,
                        )
                        continue
                    # Antigüedad del perfil: lo viejo ni se guarda.
                    found = orch.filter_by_age(found, max_age_days)
                    summary["found"] += len(found)
                    try:
                        saved = orch.save_batch(
                            db, found, search_query=query,
                            search_profile_id=str(profile_id),
                            uid=uid, email=email,
                        )
                    except Exception as error:  # noqa: BLE001
                        summary["errors"].append(
                            f"guardado {source}/{query}: {str(error)[:150]}"
                        )
                        continue
                    rows.extend(saved)
                    time.sleep(0.5)
                if rows:
                    try:
                        stats = orch.analyze_batch(
                            db, scraper=scraper, profile=user_profile,
                            rows=rows, max_details=8, delay=0.5,
                            uid=uid, email=email,
                        )
                        summary["analyzed"] += stats["analyzed"]
                        summary["relevant"] += stats["relevant"]
                    except Exception as error:  # noqa: BLE001
                        summary["errors"].append(
                            f"analisis {source}: {str(error)[:150]}"
                        )

            # Nuevas = vistas por primera vez en esta ejecucion.
            new_ids = _count_new(db, started_at, str(profile_id))
            summary["new"] = len(new_ids)
            profiles.touch_run(
                db, profile_id, status="ok", found=summary["found"],
                new=summary["new"], now=datetime.utcnow(),
            )
        finally:
            _running_profiles.discard(str(profile_id))
        return summary
    finally:
        if owns_db:
            _close_db(db, needs_close)


def run_due_profiles(*, db=None) -> dict:
    """Ejecuta perfiles activos vencidos (next_run_at <= ahora)."""
    from app.services import search_profiles as profiles

    owns_db = db is None
    if owns_db:
        db, needs_close = _new_db()
    else:
        needs_close = False
    now = datetime.utcnow()
    result = {"at": now.isoformat(), "ran": [], "skipped": 0, "error": None}
    try:
        for profile in profiles.list_profiles(db):
            if not profile.get("active"):
                continue
            next_run = profile.get("next_run_at")
            if next_run:
                try:
                    if datetime.fromisoformat(str(next_run)) > now:
                        continue
                except ValueError:
                    pass
            # Obtener uid/email del dueño del perfil
            owner_uid = profile.get("owner_uid")
            is_demo = profile.get("is_demo")
            # Para perfiles demo (invitados), usar GUEST_OWNER
            if is_demo:
                from app.services.search_profiles import GUEST_OWNER
                uid = GUEST_OWNER
                email = ""
            else:
                uid = owner_uid
                email = ""  # No tenemos email en el perfil, se puede obtener si se necesita
            summary = run_profile(profile["id"], db=db, uid=uid, email="")
            result["ran"].append({
                "profile_id": profile["id"],
                "name": profile.get("name"),
                "found": summary["found"],
                "new": summary["new"],
                "errors": len(summary["errors"]),
            })
        _last_tick.update({
            "at": now.isoformat(),
            "profiles": len(result["ran"]),
            "new": sum(r["new"] for r in result["ran"]),
            "error": None,
        })
    except Exception as error:  # noqa: BLE001
        logger.exception("Tick del scheduler fallo")
        result["error"] = str(error)[:300]
        _last_tick.update({
            "at": now.isoformat(), "profiles": 0, "new": 0,
            "error": result["error"],
        })
    finally:
        if owns_db:
            _close_db(db, needs_close)
    return result


def _tick_job() -> None:
    with _lock:
        # Fase 4: no ejecuta inline (bloquearia el hilo del scheduler
        # si un tick tarda mas que el intervalo). Encola coalescido;
        # el worker unico lo procesa y actualiza _last_tick al terminar.
        from app.services import run_queue as queue

        queue.submit_tick(wait=False)


def start_scheduler() -> bool:
    """Inicia el scheduler en proceso (idempotente). Devuelve False si
    esta deshabilitado por configuracion."""
    global _scheduler
    from app.config import SCHEDULER_ENABLED
    from app.config import SCHEDULER_INTERVAL_SECONDS

    if not SCHEDULER_ENABLED:
        logger.info("Scheduler deshabilitado (SCHEDULER_ENABLED=false).")
        return False
    if _scheduler is not None:
        return True
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("apscheduler no instalado; scheduler inactivo.")
        return False
    _scheduler = BackgroundScheduler(timezone="UTC", daemon=True)
    _scheduler.add_job(
        _tick_job, "interval", seconds=max(60, SCHEDULER_INTERVAL_SECONDS),
        id="search_tick", max_instances=1, coalesce=True,
        misfire_grace_time=300,
    )
    _scheduler.start()
    logger.info("Scheduler iniciado (tick cada %ss).",
                max(60, SCHEDULER_INTERVAL_SECONDS))
    return True


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        _scheduler = None


def scheduler_status() -> dict:
    from app.config import SCHEDULER_ENABLED
    from app.config import SCHEDULER_INTERVAL_SECONDS

    try:
        from app.services import run_queue as queue

        queue_info = queue.queue_status()
    except Exception:  # noqa: BLE001
        queue_info = {"pending": 0, "running": 0,
                      "worker_alive": False, "stored": 0}
    return {
        "enabled": bool(SCHEDULER_ENABLED and _scheduler is not None),
        "configured": bool(SCHEDULER_ENABLED),
        "interval_seconds": max(60, SCHEDULER_INTERVAL_SECONDS),
        "running_profiles": sorted(_running_profiles),
        "last_tick": dict(_last_tick),
        "queue": queue_info,
    }


def _count_new(db, started_at: datetime, profile_id: str) -> set[str]:
    """Ids con first_seen_at dentro de esta ejecucion (solo nuevas)."""
    import json

    from app.services import job_service as jobs

    fresh: set[str] = set()
    for row in jobs.iter_all_jobs(db, limit=5000):
        first = row.first_seen_at
        profiles = row.search_profile_ids or []
        if isinstance(profiles, str):
            try:
                profiles = json.loads(profiles)
            except ValueError:
                profiles = []
        if str(profile_id) not in [str(p) for p in (profiles or [])]:
            continue
        try:
            if first is not None and first >= started_at:
                fresh.add(row.id)
        except TypeError:
            continue
    return fresh
