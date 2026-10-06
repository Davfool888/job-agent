"""Router system (Fase 1: extraido de app/main.py sin cambios de logica)."""
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
@router.get("/")
def root():
    return {"app": APP_NAME, "status": "running"}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/detailed")
def health_detailed():
    """Diagnostico sin efectos secundarios.

    Solo lectura (ping de Firestore o chequeo de URL sqlite), sin
    arrancar workers. Nunca lanza 500: todo fallo se reporta como
    {"reachable": False, "error": ...}.
    """
    import shutil as _shutil

    from app.config import DB_BACKEND

    def _chromium() -> dict:
        try:
            from app.adapt.pdf import chromium_available

            return {"available": bool(chromium_available())}
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}

    def _scheduler() -> dict:
        try:
            from app import scheduler as _sched
            from app.config import SCHEDULER_ENABLED

            return {
                "enabled": bool(SCHEDULER_ENABLED),
                "running": bool(getattr(_sched, "_scheduler", None) is not None),
            }
        except Exception as exc:  # noqa: BLE001
            return {"enabled": False, "error": str(exc)}

    def _database() -> dict:
        from app.config import DB_BACKEND as _backend
        from app.config import FIREBASE_PROJECT_ID as _project

        info: dict = {"backend": _backend, "reachable": False}
        if _backend == "firestore":
            info["project"] = _project or None
            try:
                from app.database.firestore_client import FirestoreDatabase

                client = FirestoreDatabase().client
                # Ping barato de lectura (no escribe nada).
                list(client.collections())
                info["reachable"] = True
            except Exception as exc:  # noqa: BLE001
                info["error"] = str(exc)[:300]
        else:
            import os as _os

            from app.config import DATABASE_URL

            info["url"] = DATABASE_URL
            info["reachable"] = True
            info["ephemeral_warning"] = (
                not bool(_os.getenv("ALLOW_EPHEMERAL_SQLITE")))
        return info

    return {
        "status": "ok",
        "db_backend": DB_BACKEND,
        "database": _database(),
        "chromium": _chromium(),
        "pdflatex": {"available": _shutil.which("pdflatex") is not None},
        "scheduler": _scheduler(),
    }


@router.get("/stats")
def stats(request: Request, db: Session = Depends(get_db)):
    """Resumen agregado con datos reales (para el dashboard)."""
    uid, email = _profile_identity(request)
    return get_stats(db, uid=uid, email=email)


@router.get("/analytics")
def analytics(request: Request, db: Session = Depends(get_db)):
    """Analytics Agent: distribuciones, skills, fuentes, CVs (§19)."""
    from app.agents.analytics_agent import summarize

    uid, email = _profile_identity(request)
    return summarize(db, uid=uid, email=email)


@router.get("/ai/status")
def ai_status():
    """Proveedores IA disponibles (sin exponer keys)."""
    from app.ai.router import get_router

    return {
        "order": [p.name for p in get_router().providers],
        "providers": get_router().providers_status(),
    }


@router.get("/sources")
def list_sources():
    """Fuentes de empleo disponibles para /jobs/search?source=..."""
    from app.config import COMPUTRABAJO_ENABLED
    from app.config import LINKEDIN_ENABLED

    return {
        "sources": registry.available_sources(),
        "enabled": {
            "computrabajo": COMPUTRABAJO_ENABLED,
            "linkedin": LINKEDIN_ENABLED,
        },
    }


