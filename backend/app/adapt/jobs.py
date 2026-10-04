"""Cola asincrona de Adaptar-perfil (POST rapido + polling).

El endpoint sync POST /jobs/{id}/adapt-cv genera el PDF dentro del
request (Chromium en plan gratuito > 90s -> el frontend aborta y muestra
"no respondio a tiempo"). Este modulo lo vuelve asincrono:

- start_adapt_job(): valida rapido (job + perfil) y lanza un hilo daemon
  con su propia sesion de BD; responde 202 de inmediato.
- Estado en disco: adapt_dir(job_id)/status.json {processing|done|error}.
  Sobrevive a reintentos del cliente dentro de la misma instancia; si la
  instancia reinicia, el estado "processing" viejo se marca STALE.
- get_adapt_status(): lee el estado para el polling del frontend.

Errores con codigo (nunca trazas): los mismos AdaptError del flujo sync.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# Evita lanzar dos workers para el mismo job a la vez.
_locks_lock = threading.Lock()
_running: set[str] = set()

# Un "processing" mas viejo que esto se considera muerto (reinicio del
# servidor con disco efimero, crash del worker).
STALE_PROCESSING_SECONDS = 15 * 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_path(job_id, uid: str | None = None,
                 email: str | None = None) -> Path:
    from app.adapt.service import adapt_dir

    return adapt_dir(job_id, uid, email) / "status.json"


def _read_status(job_id, uid: str | None = None,
                 email: str | None = None) -> dict | None:
    path = _status_path(job_id, uid, email)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_status(job_id, payload: dict, uid: str | None = None,
                  email: str | None = None) -> None:
    path = _status_path(job_id, uid, email)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _is_stale(status: dict | None) -> bool:
    if not status or status.get("status") != "processing":
        return True
    try:
        started = datetime.fromisoformat(str(status.get("started_at", "")))
        age = (datetime.now(timezone.utc) - started).total_seconds()
        return age > STALE_PROCESSING_SECONDS
    except ValueError:
        return True


def _owner_status_key(uid: str | None, email: str | None,
                      job_id) -> str:
    from app.adapt.service import _owner_key

    return f"{_owner_key(uid, email)}:{job_id}"


def start_adapt_job(job_id, uid: str | None = None,
                    email: str | None = None) -> dict:
    """Valida rapido y lanza el worker. Responde de inmediato.

    Devuelve {"accepted": True, "job_id", "status": "processing"|"done"}.
    Lanza AdaptError en validaciones rapidas (job inexistente, perfil
    incompleto) para que el cliente las muestre sin polling.
    """
    from app.adapt.service import AdaptError

    key = _owner_status_key(uid, email, job_id)
    with _locks_lock:
        if key in _running:
            return {"accepted": True, "job_id": str(job_id),
                    "status": "processing"}
    current = _read_status(job_id, uid, email)
    if current and current.get("status") == "processing" and not _is_stale(current):
        return {"accepted": True, "job_id": str(job_id),
                "status": "processing"}

    _write_status(job_id, {
        "status": "processing",
        "job_id": str(job_id),
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
    }, uid, email)
    with _locks_lock:
        _running.add(key)
    thread = threading.Thread(
        target=_run_in_background, args=(job_id, uid, email), daemon=True)
    thread.start()
    # Validaciones rapidas ya pasaron arriba si se llamo a
    # prevalidate_adapt_job(); el worker reporta el resto por status.
    return {"accepted": True, "job_id": str(job_id), "status": "processing"}


def prevalidate_adapt_job(db, job_id, uid: str | None = None,
                          email: str | None = None) -> None:
    """Chequeos baratos (sin Chromium) antes de aceptar el trabajo.

    Lanza AdaptError con codigo: JOB_NOT_FOUND, PROFILE_INCOMPLETE,
    JOB_INCOMPLETE. El endpoint los devuelve sync para mensaje inmediato.
    """
    from app.adapt.service import _as_list, _is_profile_complete, AdaptError
    from app.services.job_service import get_job_by_id
    from app.services.search_profiles import _is_guest

    try:
        job = get_job_by_id(db=db, job_id=job_id)
    except (TypeError, ValueError) as error:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.",
                         http=404) from error
    if not job:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.", http=404)
    if not (job.title or job.description):
        raise AdaptError("JOB_INCOMPLETE",
                         "La oferta no tiene datos suficientes para adaptar el CV.",
                         http=400)
    if uid and not _is_guest(uid, email):
        from app.services.job_service import get_rich_profile_for

        profile = get_rich_profile_for(db, uid, email)
        if not _is_profile_complete(profile):
            raise AdaptError(
                "PROFILE_INCOMPLETE",
                "Debe completar su perfil antes de generar un CV adaptado. "
                "Vaya a la sección de Perfil y complete los campos obligatorios.",
                http=400,
            )


def get_adapt_status(db, job_id, uid: str | None = None,
                     email: str | None = None) -> dict:
    """Estado para polling. Incluye resultado liviano cuando done."""
    from app.adapt.service import AdaptError
    from app.services.job_service import get_job_by_id

    try:
        job = get_job_by_id(db=db, job_id=job_id)
    except (TypeError, ValueError):
        job = None
    if not job:
        raise AdaptError("JOB_NOT_FOUND", "Oferta no encontrada.", http=404)
    status = _read_status(job.id, uid, email)
    if not status:
        return {"status": "idle", "job_id": job.id}
    if status.get("status") == "processing" and _is_stale(status):
        return {
            "status": "error",
            "job_id": job.id,
            "error": {
                "code": "STALE_JOB",
                "message": "El proceso se interrumpió (servidor reiniciado). "
                           "Pulsa «Adaptar perfil» de nuevo.",
            },
        }
    return {"job_id": job.id, **status}


def _run_in_background(job_id, uid: str | None,
                       email: str | None = None) -> None:
    from app.adapt.service import AdaptError, adapt_profile_for_job
    from app.scheduler import _close_db, _new_db

    key = _owner_status_key(uid, email, job_id)
    handle, needs_close = _new_db()
    try:
        result = adapt_profile_for_job(handle, job_id, uid, email)
        _write_status(job_id, {
            "status": "done",
            "job_id": str(job_id),
            "started_at": (_read_status(job_id, uid, email) or {}).get("started_at"),
            "updated_at": _now_iso(),
            "result": result,
        }, uid, email)
    except AdaptError as error:
        _write_status(job_id, {
            "status": "error",
            "job_id": str(job_id),
            "started_at": (_read_status(job_id, uid, email) or {}).get("started_at"),
            "updated_at": _now_iso(),
            "error": {"code": error.code, "message": str(error)},
        }, uid, email)
    except Exception as error:  # noqa: BLE001
        _write_status(job_id, {
            "status": "error",
            "job_id": str(job_id),
            "started_at": (_read_status(job_id, uid, email) or {}).get("started_at"),
            "updated_at": _now_iso(),
            "error": {"code": "UNKNOWN_ERROR",
                      "message": f"Fallo inesperado: {error}"[:300]},
        }, uid, email)
    finally:
        _close_db(handle, needs_close)
        with _locks_lock:
            _running.discard(key)
