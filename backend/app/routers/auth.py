"""Router auth (Fase 1: extraido de app/main.py sin cambios de logica)."""
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
@router.get("/auth/status")
def auth_status():
    """Dice si el backend puede verificar sesiones de Firebase."""
    import os as _os

    def _source() -> str:
        if _os.getenv("FIRESTORE_EMULATOR_HOST"):
            return "emulator"
        if _os.getenv("FIREBASE_SERVICE_ACCOUNT_B64"):
            return "b64"
        if _os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"):
            return "inline"
        if _os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            return "file"
        return "none"

    try:
        from app.database import firestore_client

        firestore_client.get_firestore()
        return {"configured": True, "provider": "google",
                "source": _source()}
    except Exception as exc:
        return {"configured": False, "provider": "google",
                "source": _source(), "error": str(exc)}


@router.get("/auth/me")
def auth_me(
    request: Request,
    db: Session = Depends(get_db),
):
    """Verifica el ID token (Bearer) y devuelve/crea el usuario.

    Solo guarda nombre, telefono y gmail.
    """
    from app.auth import verify_bearer_token
    from app.services.user_service import get_or_create_user

    claims = verify_bearer_token(request.headers.get("authorization"))
    user, created = get_or_create_user(
        db, claims["uid"], claims["email"], claims["name"]
    )
    return {
        **user,
        "is_new": created,
        "is_profile_complete": bool((user.get("nombre") or "").strip())
        and bool((user.get("telefono") or "").strip()),
    }


@router.put("/auth/me")
def auth_update_me(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    """Completa/actualiza nombre y telefono del usuario autenticado."""
    from app.auth import verify_bearer_token
    from app.services.user_service import get_or_create_user, update_user

    claims = verify_bearer_token(request.headers.get("authorization"))
    # Asegura que existe (primer login sin GET previo).
    get_or_create_user(db, claims["uid"], claims["email"], claims["name"])
    nombre = payload.get("nombre") if isinstance(payload, dict) else None
    telefono = payload.get("telefono") if isinstance(payload, dict) else None
    if nombre is not None and not str(nombre).strip():
        raise HTTPException(status_code=400, detail="El nombre es obligatorio.")
    if telefono is not None and not str(telefono).strip():
        raise HTTPException(status_code=400, detail="El telefono es obligatorio.")
    user = update_user(db, claims["uid"], nombre=nombre, telefono=telefono)
    return {
        **user,
        "is_profile_complete": bool((user.get("nombre") or "").strip())
        and bool((user.get("telefono") or "").strip()),
    }


@router.post("/auth/register", status_code=201)
def auth_register(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    """Registra la cuenta Google UNA sola vez (nombre + telefono).

    - Sin email (anonimo) -> 400: registrate con Google.
    - Cuenta ya registrada -> 409 ACCOUNT_EXISTS
      ("ya existe esta cuenta ingresa por login").
    - Fila vacia previa (auto-creada sin completar) -> la completa.
    """
    from fastapi.responses import JSONResponse

    from app.auth import verify_bearer_token
    from app.services.user_service import (
        get_or_create_user,
        get_user,
        update_user,
    )

    claims = verify_bearer_token(request.headers.get("authorization"))
    uid = claims["uid"]
    email = claims.get("email") or ""
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Regístrate con una cuenta de Google.",
        )
    existing = get_user(db, uid)
    if _auth_account_complete(existing):
        return JSONResponse(
            status_code=409,
            content={"code": "ACCOUNT_EXISTS",
                     "message": "ya existe esta cuenta ingresa por login"},
        )
    nombre = (payload.get("nombre") if isinstance(payload, dict) else None)
    telefono = (payload.get("telefono") if isinstance(payload, dict) else None)
    nombre = str(nombre or "").strip() or str(claims.get("name") or "").strip()
    telefono = str(telefono or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio.")
    if not telefono:
        raise HTTPException(
            status_code=400,
            detail="El teléfono es obligatorio (se pide una sola vez).",
        )
    if not existing:
        get_or_create_user(db, uid, email, nombre)
    user = update_user(db, uid, nombre=nombre, telefono=telefono)
    return JSONResponse(status_code=201, content={
        **user,
        "is_new": not existing,
        "is_profile_complete": True,
    })


@router.post("/auth/login")
def auth_login(
    request: Request,
    db: Session = Depends(get_db),
):
    """Entrada estricta: sin registro previo no deja pasar.

    - Sin email (anonimo) -> 400.
    - Sin cuenta registrada -> 404 NOT_REGISTERED
      ("tienes que registrarte").
    """
    from fastapi.responses import JSONResponse

    from app.auth import verify_bearer_token
    from app.services.user_service import get_user

    claims = verify_bearer_token(request.headers.get("authorization"))
    uid = claims["uid"]
    email = claims.get("email") or ""
    if not email:
        raise HTTPException(
            status_code=400,
            detail="Entra con una cuenta de Google.",
        )
    user = get_user(db, uid)
    if not _auth_account_complete(user):
        return JSONResponse(
            status_code=404,
            content={"code": "NOT_REGISTERED",
                     "message": "tienes que registrarte"},
        )
    return {**user, "is_profile_complete": True}


