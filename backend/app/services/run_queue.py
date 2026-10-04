"""Cola de ejecuciones pesadas (Fase 4).

Problema: `POST /search-profiles/{id}/run` y `POST /scheduler/tick`
ejecutaban scraping+analisis en el hilo del request (30-60s+,
timeout en Render/Vercel) y varios runs podian solaparse.

Solucion sin romper el contrato: una unica cola FIFO con un worker
daemon que ejecuta de a un trabajo con su propia sesion de BD.
Los endpoints, por defecto, encolan y esperan el resultado
(`?wait=true`): misma respuesta sync de siempre. Con `?wait=false`
devuelven 202 + `job_id` para polling en `GET /scheduler/jobs/*`.

Coalescencia: si ya hay un trabajo en curso/cola con la misma
clave (mismo perfil o tick global), se devuelve ese en vez de
encolar un duplicado (anti doble-click, anti tick solapado).
"""
from __future__ import annotations

import threading
import time
import uuid

MAX_STORED_JOBS = 100
DEFAULT_WAIT_TIMEOUT = 300.0

_lock = threading.Condition()
_queue: list[dict] = []
_jobs: dict[str, dict] = {}
_order: list[str] = []
_worker: threading.Thread | None = None


def _new_job(kind: str, key: str, payload: dict) -> dict:
    job = {
        "job_id": uuid.uuid4().hex[:12],
        "kind": kind,
        "key": key,
        "status": "queued",  # queued|running|done|error
        "profile_id": payload.get("profile_id"),
        "created_at": time.time(),
        "started_at": None,
        "finished_at": None,
        "result": None,
        "error": None,
        "event": threading.Event(),
    }
    return job


def _store(job: dict) -> None:
    _jobs[job["job_id"]] = job
    _order.append(job["job_id"])
    while len(_order) > MAX_STORED_JOBS:
        _jobs.pop(_order.pop(0), None)


def _find_live(key: str) -> dict | None:
    for job in _jobs.values():
        if job["key"] == key and job["status"] in ("queued", "running"):
            return job
    return None


def _ensure_worker() -> None:
    global _worker
    if _worker is not None and _worker.is_alive():
        return
    _worker = threading.Thread(target=_worker_loop, daemon=True,
                               name="run-queue-worker")
    _worker.start()


def _worker_loop() -> None:
    while True:
        with _lock:
            while not _queue:
                _lock.wait()
            job = _queue.pop(0)
            job["status"] = "running"
            job["started_at"] = time.time()
        try:
            if job["kind"] == "profile":
                from app.scheduler import run_profile

                job["result"] = run_profile(
                    job["profile_id"], uid=job.get("uid"),
                    email=job.get("email"),
                )
            elif job["kind"] == "tick":
                from app.scheduler import run_due_profiles

                job["result"] = run_due_profiles()
            else:  # pragma: no cover
                raise ValueError(f"kind desconocido: {job['kind']}")
            job["status"] = "done"
        except Exception as error:  # noqa: BLE001
            job["status"] = "error"
            job["error"] = str(error)[:500]
        finally:
            job["finished_at"] = time.time()
            job["event"].set()


def submit(kind: str, key: str, payload: dict | None = None,
           wait: bool = True,
           timeout: float = DEFAULT_WAIT_TIMEOUT) -> tuple[dict, bool]:
    """Encola (o reutiliza si hay uno vivo con la misma clave).

    Devuelve (job_publico, completed). Con wait=True espera hasta
    `timeout`; si expira, completed=False y el cliente debe hacer
    polling. El dict devuelto es una vista sin el Event interno.
    """
    with _lock:
        live = _find_live(key)
        if live is not None:
            job = live
        else:
            job = _new_job(kind, key, payload or {})
            job.update({k: v for k, v in (payload or {}).items()
                        if k in ("uid", "email", "profile_id")})
            _store(job)
            _queue.append(job)
            _lock.notify()
        _ensure_worker()
    if wait:
        job["event"].wait(timeout)
    return public_job(job), job["status"] in ("done", "error")


def submit_profile_run(profile_id, uid=None, email=None, wait=True,
                       timeout=DEFAULT_WAIT_TIMEOUT):
    return submit("profile", f"profile:{profile_id}",
                  {"profile_id": str(profile_id), "uid": uid,
                   "email": email}, wait=wait, timeout=timeout)


def submit_tick(wait=True, timeout=DEFAULT_WAIT_TIMEOUT):
    return submit("tick", "tick:global", {}, wait=wait, timeout=timeout)


def public_job(job: dict) -> dict:
    return {k: job.get(k) for k in (
        "job_id", "kind", "profile_id", "status", "created_at",
        "started_at", "finished_at", "result", "error")}


def get_job(job_id: str) -> dict | None:
    job = _jobs.get(str(job_id))
    return public_job(job) if job else None


def list_jobs(limit: int = 20) -> list[dict]:
    return [public_job(_jobs[jid]) for jid in reversed(_order[-limit:])]


def queue_status() -> dict:
    with _lock:
        pending = sum(1 for j in _queue)
        running = sum(1 for j in _jobs.values()
                      if j["status"] == "running")
        alive = _worker is not None and _worker.is_alive()
    return {"pending": pending, "running": running,
            "worker_alive": alive, "stored": len(_jobs)}


def reset_for_tests() -> None:
    """Vacía la cola (solo tests). No detiene el worker."""
    with _lock:
        _queue.clear()
        _jobs.clear()
        _order.clear()
