"""Router search_profiles (Fase 1: extraido de app/main.py sin cambios de logica)."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import APP_NAME
from app.database.connection import get_db
from app.database.models import JOB_STATUSES
from app.database.models import Job  # noqa: F401
from app.database.models import PDFConfig  # noqa: F401
from app.database.models import Profile  # noqa: F401
from app.database.models import ProfileCV  # noqa: F401
from app.database.models import User  # noqa: F401
from app.database.models import UserProfile  # noqa: F401
from app.database.models import UserRichProfile  # noqa: F401
from app.schemas.job import JobResponse
from app.schemas.job import JobStatusUpdate
from app.scraper import registry
from app.services.job_service import analyze_pending
from app.services.job_service import get_all_jobs
from app.services.job_service import get_job_by_id
from app.services.job_service import get_profile
from app.services.job_service import get_profile_for
from app.services.job_service import get_stats
from app.services.job_service import save_analysis
from app.services.job_service import save_jobs
from app.services.job_service import save_profile
from app.services.job_service import update_job_status
from .common import _adapt_identity
from .common import _auth_account_complete
from .common import _json_list
from .common import _pdf_config_to_out
from .common import _profile_identity
from .common import PDFConfigIn
from .common import PDFConfigOut

router = APIRouter()
@router.get("/search-profiles")
def list_search_profiles(request: Request, db: Session = Depends(get_db)):
    """Perfiles de busqueda visibles para la sesion (admin: todos;
    invitado: demos; otros: solo los suyos)."""
    from app.services import search_profiles as profiles

    return profiles.list_profiles_for(db, *_profile_identity(request))


@router.post("/search-profiles", status_code=201)
def create_search_profile(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    from app.services import search_profiles as profiles

    try:
        return profiles.create_profile_for(
            db, payload or {}, *_profile_identity(request))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/search-profiles/{profile_id}")
def get_search_profile(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    from app.services import search_profiles as profiles

    profile = profiles.get_profile_for(
        db, profile_id, *_profile_identity(request))
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return profile


@router.put("/search-profiles/{profile_id}")
def update_search_profile(
    profile_id: str,
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    from app.services import search_profiles as profiles

    try:
        profile = profiles.update_profile_for(
            db, profile_id, payload or {}, *_profile_identity(request))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return profile


@router.delete("/search-profiles/{profile_id}", status_code=204)
def delete_search_profile(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    from app.services import search_profiles as profiles

    if not profiles.delete_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return None


@router.post("/search-profiles/{profile_id}/run")
def run_search_profile_now(
    profile_id: str, request: Request, db: Session = Depends(get_db),
    wait: bool = Query(
        True, description="true (defecto): espera el resultado sync. "
        "false: devuelve 202 + job_id para polling."),
):
    """Ejecuta un perfil manualmente sin esperar su frecuencia.

    Fase 4: el scraping corre en el worker unico (no en el hilo del
    request y sin solapar runs). Por defecto espera y devuelve el
    mismo resumen de siempre; con ?wait=false devuelve 202.
    """
    from app.services import run_queue as queue
    from app.services import search_profiles as profiles

    if not profiles.get_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    try:
        uid, email = _profile_identity(request)
        job, completed = queue.submit_profile_run(
            profile_id, uid=uid, email=email, wait=wait)
        if not completed:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=202, content={
                "job_id": job["job_id"], "status": job["status"],
                "kind": "profile", "profile_id": str(profile_id),
            })
        if job["status"] == "error":
            raise HTTPException(
                status_code=502, detail=f"Run fallo: {job['error']}")
        return job["result"]
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Run fallo: {error}")


@router.post("/search-profiles/{profile_id}/cv", status_code=201)
async def upload_search_profile_cv(
    profile_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Sube el CV de referencia del perfil (PDF, max 10 MB).

    Uno por perfil: reemplazar sube de nuevo. El texto extraido queda
    como ejemplo para generar CVs personalizados de sus ofertas."""
    from app.services import profile_cvs as pcvs
    from app.services import search_profiles as profiles

    if not profiles.get_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    filename = (file.filename if file else "") or "cv.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Solo se aceptan archivos PDF.")
    try:
        content = await file.read()
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail=f"No se pudo leer el archivo: {error}")
    try:
        return pcvs.save_profile_cv(db, profile_id, filename, content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/search-profiles/{profile_id}/cv")
def get_search_profile_cv(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    """Estado del CV de referencia del perfil."""
    from app.services import profile_cvs as pcvs
    from app.services import search_profiles as profiles

    if not profiles.get_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    meta = pcvs.get_profile_cv(db, profile_id)
    if not meta:
        return {"profile_id": str(profile_id), "has_cv": False}
    return {**meta, "has_cv": True}


@router.get("/search-profiles/{profile_id}/cv/download")
def download_search_profile_cv(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    """Descarga el PDF de referencia del perfil."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.services import profile_cvs as pcvs
    from app.services import search_profiles as profiles

    if not profiles.get_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    meta = pcvs.get_profile_cv(db, profile_id)
    target = pcvs.pdf_path(profile_id)
    if not meta or not Path(target).exists():
        raise HTTPException(
            status_code=404, detail="Este perfil no tiene CV de referencia.")
    return FileResponse(
        path=str(target),
        filename=meta["filename"],
        media_type="application/pdf",
        content_disposition_type="inline",
    )


@router.delete("/search-profiles/{profile_id}/cv", status_code=204)
def delete_search_profile_cv(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    """Elimina el CV de referencia del perfil (archivo + metadatos)."""
    from app.services import profile_cvs as pcvs
    from app.services import search_profiles as profiles

    if not profiles.get_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    if not pcvs.delete_profile_cv(db, profile_id):
        raise HTTPException(
            status_code=404, detail="Este perfil no tiene CV de referencia.")
    return None


@router.get("/scheduler/status")
def scheduler_status():
    """Estado del programador interno (ultimo tick, perfiles en curso)."""
    from app.scheduler import scheduler_status as status

    return status()


@router.post("/scheduler/tick")
def scheduler_tick(
    request: Request,
    secret: str | None = Query(None),
    wait: bool = Query(
        True, description="true (defecto): espera el resultado sync. "
        "false: devuelve 202 + job_id para polling."),
):
    """Ejecuta perfiles vencidos. Lo llama el scheduler interno y,
    opcionalmente, un cron externo (cron-job.org) cuando Render duerme.
    Si SCHEDULER_CRON_SECRET esta configurado, exige ?secret= o
    header X-Cron-Secret.

    Fase 4: corre en el worker unico (coalescido si ya hay un tick en
    curso). Por defecto espera y devuelve lo mismo de siempre.
    """
    from app.config import SCHEDULER_CRON_SECRET
    from app.services import run_queue as queue

    if SCHEDULER_CRON_SECRET:
        header_secret = request.headers.get("X-Cron-Secret")
        if secret != SCHEDULER_CRON_SECRET and (
            header_secret != SCHEDULER_CRON_SECRET
        ):
            raise HTTPException(status_code=401, detail="No autorizado.")
    try:
        job, completed = queue.submit_tick(wait=wait)
        if not completed:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=202, content={
                "job_id": job["job_id"], "status": job["status"],
                "kind": "tick",
            })
        if job["status"] == "error":
            raise HTTPException(
                status_code=502, detail=f"Tick fallo: {job['error']}")
        return job["result"]
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Tick fallo: {error}")


@router.get("/scheduler/jobs")
def scheduler_jobs(limit: int = Query(20, ge=1, le=100)):
    """Ultimos trabajos de la cola (Fase 4, polling para ?wait=false)."""
    from app.services import run_queue as queue

    return {"jobs": queue.list_jobs(limit=limit)}


@router.get("/scheduler/jobs/{job_id}")
def scheduler_job(job_id: str):
    """Estado de un trabajo (queued|running|done|error + resultado)."""
    from fastapi.responses import JSONResponse

    from app.services import run_queue as queue

    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    if job["status"] in ("queued", "running"):
        return JSONResponse(status_code=202, content=job)
    return job


