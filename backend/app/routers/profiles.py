"""Router profiles (Fase 1: extraido de app/main.py sin cambios de logica)."""
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
@router.get("/pdf-config", response_model=PDFConfigOut)
def get_pdf_config(
    request: Request,
    db: Session = Depends(get_db),
):
    """Obtiene la configuración de PDF del usuario autenticado."""
    from app.auth import verify_bearer_token
    from app.services.pdf_config import get_pdf_config as _get_cfg

    claims = verify_bearer_token(request.headers.get("authorization"))
    uid = claims["uid"]

    return _pdf_config_to_out(_get_cfg(db, uid))


@router.put("/pdf-config", response_model=PDFConfigOut)
def update_pdf_config(
    payload: PDFConfigIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """Actualiza la configuración de PDF del usuario autenticado."""
    from app.auth import verify_bearer_token
    from app.services.pdf_config import update_pdf_config as _update_cfg

    claims = verify_bearer_token(request.headers.get("authorization"))
    uid = claims["uid"]

    fields = payload.model_dump(exclude_unset=True)
    try:
        return _pdf_config_to_out(_update_cfg(db, uid, fields))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/pdf-config/reset", response_model=PDFConfigOut)
def reset_pdf_config(
    request: Request,
    db: Session = Depends(get_db),
):
    """Resetea la configuración de PDF a valores por defecto."""
    from app.auth import verify_bearer_token
    from app.services.pdf_config import reset_pdf_config as _reset_cfg

    claims = verify_bearer_token(request.headers.get("authorization"))
    uid = claims["uid"]

    return _pdf_config_to_out(_reset_cfg(db, uid))


@router.get("/profile")
def read_profile(request: Request, db: Session = Depends(get_db)):
    """Perfil plano. Con sesion no-admin devuelve SOLO su perfil
    (en blanco si nunca guardo); el admin ve el base global."""
    return get_profile_for(db, *_profile_identity(request))


@router.put("/profile")
def write_profile(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    from app.services.job_service import save_profile_for

    return save_profile_for(db, *_profile_identity(request), payload or {})


@router.get("/catalogs")
def read_catalogs():
    """Catalogos normalizados (titulos, modalidades, niveles, idiomas,
    ciudades...). Fuente unica para la UI; evita duplicarlos."""
    from app.profile import catalogs

    return catalogs.get_catalogs()


@router.get("/profile/full")
def read_full_profile(request: Request, db: Session = Depends(get_db)):
    """Perfil modular completo. No-admin: en blanco hasta que guarda;
    jamas expone base_cv.json."""
    from app.services.job_service import get_rich_profile_for

    return get_rich_profile_for(db, *_profile_identity(request))


@router.put("/profile/full")
def write_full_profile(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    """Guarda el perfil estructurado. No-admin escribe solo su
    registro; nunca toca base_cv.json."""
    from app.services.job_service import save_rich_profile_for

    try:
        return save_rich_profile_for(
            db, *_profile_identity(request), payload or {})
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/profile/import-pdf")
async def import_pdf_profile(
    request: Request,
    apply: bool = Query(
        False,
        description="Si true, persiste lo extraido en el perfil del "
        "usuario (o base_cv.json si es admin). Si false (defecto), solo "
        "devuelve vista previa para revision.",
    ),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Importa un CV en PDF y lo convierte a perfil estructurado.

    Acepta multipart 'file' (.pdf) o JSON {'text': '...'} (texto ya
    extraido, util para reintentos). Las mismas garantias que
    /profile/import-latex: nada inventado, educacion formal separada
    de cursos, una descripcion por entrada.
    """
    from app.cv.pdf_import import extract_pdf_text, parse_pdf_profile

    text = ""
    filename = ""
    if file is not None:
        filename = file.filename or ""
        raw = await file.read()
        if not raw.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400, detail="El archivo no es un PDF valido.")
        if len(raw) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400, detail="El PDF supera el maximo de 10 MB.")
        try:
            text = extract_pdf_text(raw)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
    elif request is not None:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if isinstance(body, dict):
            text = str(body.get("text") or "")
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Envia un archivo .pdf (multipart 'file') o "
            "JSON {'text': '...'} con el contenido.",
        )
    try:
        result = parse_pdf_profile(text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    response: dict = {
        "filename": filename,
        "profile": result["profile"],
        "warnings": result["warnings"],
        "applied": False,
    }
    if apply:
        from app.config import is_admin_email
        from app.services.job_service import save_rich_profile
        from app.services.job_service import save_rich_profile_for

        uid, email = _profile_identity(request)
        if uid and not is_admin_email(email):
            saved = save_rich_profile_for(db, uid, email, result["profile"])
        else:
            saved = save_rich_profile(result["profile"], db=db)
        response["applied"] = True
        if isinstance(saved, dict):
            response["warnings"] = saved.get("warnings",
                                             result["warnings"])
    return response


@router.post("/profile/import-latex")
async def import_latex_profile(
    request: Request,
    apply: bool = Query(
        False,
        description="Si true, persiste lo extraido en base_cv.json. "
        "Si false (defecto), solo devuelve vista previa para revision.",
    ),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """Importa un CV en LaTeX (.tex por multipart o texto en JSON
    {"latex": "..."}) y lo convierte a perfil estructurado.

    NO inventa nada: todo viene literalmente del .tex. Las secciones no
    reconocidas se reportan en warnings en vez de adivinarse.
    """
    from app.config import BASE_CV_PATH
    from app.cv.latex_import import parse_latex_profile

    tex_text = ""
    filename = ""
    if file is not None:
        filename = file.filename or ""
        raw = await file.read()
        try:
            tex_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            tex_text = raw.decode("latin-1")
    elif request is not None:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if isinstance(body, dict):
            tex_text = str(body.get("latex") or "")
    if not tex_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Envia un archivo .tex (multipart 'file') o "
            "JSON {'latex': '...'} con el contenido.",
        )
    try:
        result = parse_latex_profile(tex_text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    response: dict = {
        "filename": filename,
        "profile": result["profile"],
        "warnings": result["warnings"],
        "style": result["style"],
        "applied": False,
    }
    if apply:
        from app.config import is_admin_email
        from app.services.job_service import save_rich_profile
        from app.services.job_service import save_rich_profile_for

        uid, email = _profile_identity(request)
        if uid and not is_admin_email(email):
            # No-admin: guarda en SU registro, nunca en base_cv.json.
            saved = save_rich_profile_for(db, uid, email, result["profile"])
        else:
            saved = save_rich_profile(result["profile"], db=db)
            BASE_CV_PATH.parent.mkdir(parents=True, exist_ok=True)
            (BASE_CV_PATH.parent / "base_cv.tex").write_text(
                tex_text, encoding="utf-8"
            )
        response["applied"] = True
        response["warnings"] = saved.get("warnings", result["warnings"])
    return response


