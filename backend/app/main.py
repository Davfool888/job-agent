from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends
from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from fastapi import UploadFile
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session

from app.config import APP_NAME
from app.config import FRONTEND_ORIGINS
from app.database.connection import Base
from app.database.connection import SessionLocal
from app.database.connection import engine
from app.database.connection import ensure_columns
from app.database.connection import get_db
from app.database.models import JOB_STATUSES
from app.database.models import Job  # noqa: F401  (registra el modelo)
from app.database.models import Profile  # noqa: F401
from app.database.models import ProfileCV  # noqa: F401
from app.database.models import User  # noqa: F401
from app.database.models import UserProfile  # noqa: F401
from app.database.models import UserRichProfile  # noqa: F401
from app.schemas.job import JobResponse
from app.schemas.job import JobStatusUpdate
from app.scraper.registry import available_sources
from app.scraper.registry import get_scraper
from app.services.job_service import analyze_pending
from app.services.job_service import backfill_fingerprints
from app.services.job_service import get_all_jobs
from app.services.job_service import get_job_by_id
from app.services.job_service import get_profile
from app.services.job_service import get_profile_for
from app.services.job_service import get_stats
from app.services.job_service import save_analysis
from app.services.job_service import save_jobs
from app.services.job_service import save_profile
from app.services.job_service import update_job_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.config import DB_BACKEND

    if DB_BACKEND == "firestore":
        # Firestore crea colecciones al primer write; solo backfill.
        from app.database.firestore_client import FirestoreDatabase

        db = FirestoreDatabase()
        backfill_fingerprints(db)
    else:
        Base.metadata.create_all(bind=engine)
        ensure_columns()
        db = SessionLocal()
        try:
            backfill_fingerprints(db)
        finally:
            db.close()
    # Scheduler en proceso (no arranca bajo pytest para no interferir).
    import os as _os
    import sys as _sys

    under_test = (
        "PYTEST_CURRENT_TEST" in _os.environ
        or "pytest" in (_sys.argv[0] if _sys.argv else "")
    )
    if not under_test:
        from app.scheduler import start_scheduler

        start_scheduler()
        # Precalienta Chromium para Adaptar-perfil (instala en fondo
        # si falta; nunca bloquea el arranque).
        try:
            from app.adapt.pdf import warmup_chromium

            warmup_chromium()
        except Exception:  # noqa: BLE001
            pass
    yield
    from app.scheduler import stop_scheduler

    stop_scheduler()


app = FastAPI(title=APP_NAME, version="0.5.0", lifespan=lifespan)

# Necesario para que el frontend (Vite local y Vercel en produccion)
# pueda llamar a la API. Origenes en config.FRONTEND_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"app": APP_NAME, "status": "running"}


def _json_list(value) -> list:
    import json as _json

    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = _json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/status")
def auth_status():
    """Dice si el backend puede verificar sesiones de Firebase."""
    try:
        from app.database import firestore_client

        firestore_client.get_firestore()
        return {"configured": True, "provider": "google"}
    except Exception as exc:
        return {"configured": False, "provider": "google", "error": str(exc)}


@app.get("/auth/me")
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


@app.put("/auth/me")
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


@app.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Resumen agregado con datos reales (para el dashboard)."""
    return get_stats(db)


@app.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    """Analytics Agent: distribuciones, skills, fuentes, CVs (§19)."""
    from app.agents.analytics_agent import summarize

    return summarize(db)


@app.get("/ai/status")
def ai_status():
    """Proveedores IA disponibles (sin exponer keys)."""
    from app.ai.router import get_router

    return {
        "order": [p.name for p in get_router().providers],
        "providers": get_router().providers_status(),
    }


def _profile_identity(request: Request) -> tuple:
    """(uid, email) de la sesion Firebase, o (None, None) sin token.

    Token presente pero invalido -> 401 (no se regala acceso legado).
    Admin sin configurar (503) -> (None, None): modo local historico."""

    raw = request.headers.get("authorization")
    if not raw:
        return None, None
    try:
        from app.auth import verify_bearer_token

        claims = verify_bearer_token(raw)
        return claims.get("uid"), claims.get("email")
    except HTTPException as exc:
        if exc.status_code == 503:
            return None, None
        raise


@app.get("/profile")
def read_profile(request: Request, db: Session = Depends(get_db)):
    """Perfil plano. Con sesion no-admin devuelve SOLO su perfil
    (en blanco si nunca guardo); el admin ve el base global."""
    return get_profile_for(db, *_profile_identity(request))


@app.put("/profile")
def write_profile(
    payload: dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
):
    from app.services.job_service import save_profile_for

    return save_profile_for(db, *_profile_identity(request), payload or {})


@app.get("/catalogs")
def read_catalogs():
    """Catalogos normalizados (titulos, modalidades, niveles, idiomas,
    ciudades...). Fuente unica para la UI; evita duplicarlos."""
    from app.profile import catalogs

    return catalogs.get_catalogs()


@app.get("/profile/full")
def read_full_profile(request: Request, db: Session = Depends(get_db)):
    """Perfil modular completo. No-admin: en blanco hasta que guarda;
    jamas expone base_cv.json."""
    from app.services.job_service import get_rich_profile_for

    return get_rich_profile_for(db, *_profile_identity(request))


@app.put("/profile/full")
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


@app.post("/profile/import-latex")
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
            saved = save_rich_profile(result["profile"])
            BASE_CV_PATH.parent.mkdir(parents=True, exist_ok=True)
            (BASE_CV_PATH.parent / "base_cv.tex").write_text(
                tex_text, encoding="utf-8"
            )
        response["applied"] = True
        response["warnings"] = saved.get("warnings", result["warnings"])
    return response


@app.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    limit: int = 200,
    status: str | None = None,
    since: str | None = Query(
        None,
        description="Solo ofertas con found_at (o created_at) posterior a "
        "esta fecha ISO. Ej: 2026-09-30T10:00:00",
    ),
    db: Session = Depends(get_db),
):
    if status and status not in JOB_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Estado invalido. Permitidos: {', '.join(JOB_STATUSES)}",
        )
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="since debe ser fecha ISO (YYYY-MM-DDTHH:MM:SS).",
            )
    return get_all_jobs(db=db, limit=limit, status=status, since=since_dt)


@app.get("/sources")
def list_sources():
    """Fuentes de empleo disponibles para /jobs/search?source=..."""
    from app.config import COMPUTRABAJO_ENABLED
    from app.config import LINKEDIN_ENABLED

    return {
        "sources": available_sources(),
        "enabled": {
            "computrabajo": COMPUTRABAJO_ENABLED,
            "linkedin": LINKEDIN_ENABLED,
        },
    }


@app.get("/search-profiles")
def list_search_profiles(request: Request, db: Session = Depends(get_db)):
    """Perfiles de busqueda visibles para la sesion (admin: todos;
    invitado: demos; otros: solo los suyos)."""
    from app.services import search_profiles as profiles

    return profiles.list_profiles_for(db, *_profile_identity(request))


@app.post("/search-profiles", status_code=201)
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


@app.get("/search-profiles/{profile_id}")
def get_search_profile(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    from app.services import search_profiles as profiles

    profile = profiles.get_profile_for(
        db, profile_id, *_profile_identity(request))
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return profile


@app.put("/search-profiles/{profile_id}")
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


@app.delete("/search-profiles/{profile_id}", status_code=204)
def delete_search_profile(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    from app.services import search_profiles as profiles

    if not profiles.delete_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    return None


@app.post("/search-profiles/{profile_id}/run")
def run_search_profile_now(
    profile_id: str, request: Request, db: Session = Depends(get_db)
):
    """Ejecuta un perfil manualmente sin esperar su frecuencia."""
    from app.scheduler import run_profile
    from app.services import search_profiles as profiles

    if not profiles.get_profile_for(
        db, profile_id, *_profile_identity(request)
    ):
        raise HTTPException(status_code=404, detail="Perfil no encontrado.")
    try:
        return run_profile(profile_id, db=db)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Run fallo: {error}")


@app.post("/search-profiles/{profile_id}/cv", status_code=201)
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


@app.get("/search-profiles/{profile_id}/cv")
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


@app.get("/search-profiles/{profile_id}/cv/download")
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
    )


@app.delete("/search-profiles/{profile_id}/cv", status_code=204)
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


@app.get("/scheduler/status")
def scheduler_status():
    """Estado del programador interno (ultimo tick, perfiles en curso)."""
    from app.scheduler import scheduler_status as status

    return status()


@app.post("/scheduler/tick")
def scheduler_tick(
    request: Request,
    secret: str | None = Query(None),
):
    """Ejecuta perfiles vencidos. Lo llama el scheduler interno y,
    opcionalmente, un cron externo (cron-job.org) cuando Render duerme.
    Si SCHEDULER_CRON_SECRET esta configurado, exige ?secret= o
    header X-Cron-Secret."""
    from app.config import SCHEDULER_CRON_SECRET
    from app.scheduler import run_due_profiles

    if SCHEDULER_CRON_SECRET:
        header_secret = request.headers.get("X-Cron-Secret")
        if secret != SCHEDULER_CRON_SECRET and (
            header_secret != SCHEDULER_CRON_SECRET
        ):
            raise HTTPException(status_code=401, detail="No autorizado.")
    try:
        return run_due_profiles()
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Tick fallo: {error}")


@app.get("/discovery/packs")
def discovery_packs():
    """Capas de busqueda disponibles (titulos, habilidades,
    responsabilidades) para POST /jobs/discover."""
    from app.analysis.discovery import PACKS

    return {
        "packs": {name: queries for name, queries in PACKS.items()},
        "counts": {name: len(queries) for name, queries in PACKS.items()},
    }


@app.post("/jobs/discover")
def discover_jobs(
    payload: dict[str, Any],
    db: Session = Depends(get_db),
):
    """Descubrimiento por capas: ejecuta N queries (titulos +
    habilidades + responsabilidades), guarda sin duplicar
    (URL + huella), trae detalles priorizados y analiza todo
    contra el perfil. Nunca borra ofertas: lo poco relevante se
    guarda con score bajo para revision."""
    from app.analysis.discovery import PACKS
    from app.analysis.discovery import discover

    source = str(payload.get("source") or "computrabajo")
    packs = payload.get("packs") or ["titles", "skills", "responsibilities"]
    queries = payload.get("queries")
    if isinstance(packs, str):
        packs = [packs]
    try:
        pages = max(1, min(int(payload.get("pages") or 1), 5))
        max_details = max(0, min(int(payload.get("max_details", 15)), 60))
        return discover(
            db,
            source=source,
            packs=list(packs),
            queries=list(queries) if queries else None,
            pages=pages,
            max_details=max_details,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Error en descubrimiento: {error}"
        )


@app.post("/jobs/analyze-pending")
def analyze_pending_endpoint(
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
):
    """Analiza en lote filas con descripcion pero sin score."""
    limit = int((payload or {}).get("limit", 50))
    return analyze_pending(db, limit=limit)


@app.post("/jobs/{job_id}/analyze")
def analyze_job_endpoint(job_id: str, db: Session = Depends(get_db)):
    """Analiza una oferta (trae detalle si falta) y persiste el
    resultado: match_score, detected_role, category, evidence,
    matched/missing skills. Ver §14."""
    from app.agents.job_analyzer import JobAnalyzer

    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")

    if not job.description:
        try:
            detail = get_scraper(job.source or "computrabajo").get_job_detail(
                job.url
            )
            if detail.get("description"):
                from app.services.job_service import update_job_fields

                job = update_job_fields(
                    db, job.id, {"description": detail["description"]}
                )
        except Exception as error:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"No se pudo traer el detalle: {error}",
            )

    result = JobAnalyzer().analyze(
        {"title": job.title or "", "description": job.description or ""},
        get_profile(db),
    )
    from app.services.job_service import refresh_job

    save_analysis(
        db,
        job,
        match_score=result["match_score"],
        matched=result["matched_skills"],
        missing=result["missing_skills"],
        detected_role=result["detected_role"],
        category=result["category"],
        evidence=result["evidence"],
        experience=result["experience_required"],
    )
    job = refresh_job(db, job)
    return {
        "job": JobResponse.model_validate(job).model_dump(),
        "analysis": result,
    }


@app.post("/jobs/{job_id}/tailor")
def tailor_job_profile(job_id: str, db: Session = Depends(get_db)):
    """Perfil adaptado a la vacante: analiza la oferta, selecciona las
    perspectivas mas relevantes del perfil y combina la informacion
    (solo copia real del perfil; `adapted: true` lo distingue de la
    fuente de verdad)."""
    from app.profile.perspectives import build_tailored_profile
    from app.profile.perspectives import select_perspectives

    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")

    from app.agents.job_analyzer import JobAnalyzer

    profile = get_profile(db)
    job_dict = {
        "title": job.title or "",
        "description": job.description or "",
        "requirements": job.requirements or "",
        "responsibilities": job.responsibilities or "",
        "sector": job.sector or "",
    }
    result = JobAnalyzer().analyze(job_dict, profile)
    selection = select_perspectives(profile, job_dict, result)
    tailored = build_tailored_profile(profile, selection, job_dict, result)
    return {
        "job_id": job.id,
        "analysis": {
            "match_score": result["match_score"],
            "detected_role": result["detected_role"],
            "category": result["category"],
            "evidence": result["evidence"],
            "perspective_bonus": result.get("perspective_bonus", 0.0),
        },
        "selection": selection["selection"],
        "combined_skills": selection["combined_skills"],
        "tailored_profile": tailored,
    }


@app.post("/jobs/{job_id}/adapt-cv")
def adapt_job_cv(job_id: str, db: Session = Depends(get_db)):
    """Adaptar-perfil: matching deterministico + seleccion + HTML/CSS
    + PDF (Chromium) con el perfil ficticio de invitado. Sin LaTeX,
    sin LLM obligatorio. Errores controlados {success, error}."""
    from fastapi.responses import JSONResponse

    from app.adapt.service import adapt_profile_for_job, AdaptError, error_body

    try:
        return adapt_profile_for_job(db, job_id)
    except AdaptError as error:
        return JSONResponse(
            status_code=error.http, content=error_body(error))


@app.get("/jobs/{job_id}/adapt-cv/download")
def download_adapt_cv(
    job_id: str,
    format: str = Query("pdf", pattern="^(pdf|html)$"),
    db: Session = Depends(get_db),
):
    """Descarga el CV adaptado (pdf o html). 404 honesto si no existe."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.adapt.service import adapt_dir
    from app.services.job_service import get_job_by_id

    job = None
    try:
        job = get_job_by_id(db=db, job_id=job_id)
    except (TypeError, ValueError):
        job = None
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    from app.config import ADAPT_CVS_DIR

    target = adapt_dir(job.id) / (f"cv.{format}")
    try:
        target.resolve().relative_to(ADAPT_CVS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Archivo no disponible.")
    if not Path(target).exists():
        raise HTTPException(
            status_code=404,
            detail="Aún no hay CV adaptado. Usa «Adaptar perfil».",
        )
    return FileResponse(
        path=str(target),
        filename=f"cv_adaptado_job_{job.id}.{format}",
        media_type="application/pdf" if format == "pdf" else "text/html",
    )



# IMPORTANTE: /jobs/search debe ir ANTES de /jobs/{job_id},
# si no FastAPI interpreta "search" como un job_id.
@app.get("/jobs/search")
def search_jobs(
    q: str = Query(..., min_length=2, description="Ej: desarrollador python"),
    pages: int = Query(1, ge=1, le=10),
    details: bool = Query(False, description="Traer descripcion completa"),
    source: str = Query(
        "computrabajo", description="Fuente: computrabajo | magneto | ..."
    ),
    analyze: bool = Query(
        True,
        description="Analizar ofertas tras el scraping (match_score, "
        "detected_role, evidence). Poner false para solo guardar.",
    ),
    max_details: int = Query(
        10, ge=0, le=30, description="Detalles a traer para ofertas sin descripcion"
    ),
    location: str | None = Query(
        None,
        description="Filtrar por ciudad antes de guardar "
        "(ej: Bogotá, Medellín). LinkedIn e Indeed lo aplican en el "
        "sitio; el resto filtra por texto de ubicación.",
    ),
    max_age_days: int = Query(
        0, ge=0, le=60,
        description="Antigüedad maxima en dias (0 = todas). "
        "Descarta ofertas con publicacion mas vieja antes de guardar.",
    ),
    db: Session = Depends(get_db),
):
    if not q.strip():
        raise HTTPException(
            status_code=400, detail="La consulta no puede estar vacia."
        )

    try:
        scraper = get_scraper(source)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    try:
        jobs = scraper.search(
            q, max_pages=pages, include_details=details, location=location
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando {scraper.source}: {error}",
        )

    # Antigüedad maxima: filtra antes de guardar (no se repite ni se
    # guarda lo viejo). Sin fecha de publicacion se conserva.
    from app.scraper.base import filter_by_max_age

    found_total = len(jobs)
    jobs = filter_by_max_age(jobs, max_age_days)

    saved_jobs = save_jobs(db=db, jobs=jobs, search_query=q)

    # Analisis despues del scraping (no solo mostrar resultados):
    # trae detalle donde falta, clasifica rol por contenido y persiste
    # match_score/matching/missing/evidence (mismo pipeline que discover).
    analyzed = 0
    relevant = 0
    details_fetched = 0
    if analyze and saved_jobs:
        from app.analysis.discovery import enrich_and_analyze
        from app.services.job_service import get_profile

        stats = enrich_and_analyze(
            db,
            scraper=scraper,
            profile=get_profile(db),
            rows=saved_jobs,
            max_details=max_details,
            delay=0,
        )
        analyzed = stats["analyzed"]
        relevant = stats["relevant"]
        details_fetched = stats["details_fetched"]
        from app.services.job_service import refresh_job

        saved_jobs = [refresh_job(db, job) for job in saved_jobs]

    return {
        "query": q,
        "pages": pages,
        "source": scraper.source,
        "location": location,
        "max_age_days": max_age_days,
        "found": found_total,
        "filtered_out": found_total - len(jobs),
        "saved": len(saved_jobs),
        "analyzed": analyzed,
        "relevant": relevant,
        "details_fetched": details_fetched,
        "jobs": [
            {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "source": job.source,
                "description": job.description,
                "match_score": job.match_score,
                "detected_role": job.detected_role,
                "category": job.category,
            }
            for job in saved_jobs
        ],
    }


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    return job


@app.get("/jobs/{job_id}/analysis")
def get_job_analysis(job_id: str, db: Session = Depends(get_db)):
    """Analisis estructurado guardado (§5, §14)."""
    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    return {
        "job_id": job.id,
        "match_score": job.match_score,
        "detected_role": job.detected_role,
        "category": job.category,
        "evidence": _json_list(job.evidence),
        "matching_skills": _json_list(job.matched_skills),
        "missing_skills": _json_list(job.missing_skills),
        "discovered_by": _json_list(job.discovered_by),
        "experience_required": job.experience_required,
        "analyzed": job.match_score is not None,
    }


@app.post("/jobs/{job_id}/cv")
def generate_job_cv(
    job_id: str,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
):
    """Genera CV para la oferta (§10-§13): respeta umbrales salvo
    force=true. Estructura: data/cvs/job_<ID>/{analysis.json,
    cv_content.json, cv.tex, cv.pdf?}."""
    from app.agents.cv_agent import CVAgent
    from app.ai.router import get_router
    from app.ai.schemas.cv_content import CVContent
    from app.config import CV_AUTO_THRESHOLD
    from app.config import CV_REVIEW_THRESHOLD
    from app.cv import generator as cvgen

    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")

    force = bool((payload or {}).get("force", False))
    score = job.match_score
    if score is None:
        raise HTTPException(
            status_code=400,
            detail="La oferta no tiene analisis. "
            "Llama primero a POST /jobs/{id}/analyze.",
        )

    if score >= CV_AUTO_THRESHOLD:
        decision = "auto"
    elif score >= CV_REVIEW_THRESHOLD:
        decision = "review_required" if not force else "forced"
    else:
        decision = "forced" if force else "below_threshold"
    if decision in ("review_required", "below_threshold"):
        return {
            "job_id": job.id,
            "match_score": score,
            "decision": decision,
            "thresholds": {
                "auto": CV_AUTO_THRESHOLD,
                "review": CV_REVIEW_THRESHOLD,
            },
            "cv_generated": False,
            "hint": "Repite con {\"force\": true} para generar de todos modos.",
        }

    agent = CVAgent()
    profile = agent.base_profile()
    personal = profile.get("personal", {}) if profile else {}
    skills = profile.get("skills", {}) if profile else {}
    flat_skills = (
        [s for group in skills.values() for s in (group or [])]
        if isinstance(skills, dict)
        else [s for s in (skills or [])]
    )
    has_data = bool(
        (personal.get("full_name") or "").strip()
        or (personal.get("email") or "").strip()
        or profile.get("professional_summary", "").strip()
        or profile.get("experience")
        or profile.get("projects")
        or [s for s in flat_skills if str(s).strip()]
        or profile.get("education")
    )
    if not profile or not has_data:
        raise HTTPException(
            status_code=400,
            detail="Perfil base vacio. Completa backend/data/profiles/"
            "base_cv.json primero (el CV nunca inventa datos).",
        )

    analysis = {
        "detected_role": job.detected_role,
        "category": job.category,
        "evidence": _json_list(job.evidence),
        "match_score": job.match_score,
    }
    job_dict = {"title": job.title or "", "description": job.description or ""}
    # CVs de referencia de los perfiles que encontraron esta oferta:
    # entran al prompt como ejemplos de estilo (nunca como hechos).
    from app.services import profile_cvs as pcvs

    references = pcvs.reference_texts_for_job(db, job)
    try:
        generated = get_router().generate_cv_content(
            job_dict, analysis, profile, reference_cvs=references or None
        )
        content = CVContent.model_validate(generated)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Ningun proveedor genero el CV: {error}"
        )

    personal = profile.get("personal", {}) or {}
    from app.services.job_service import is_firestore_handle
    from app.services.job_service import update_job_fields

    result = cvgen.generate_for_job(
        job.id,
        content,
        personal,
        analysis={**analysis, "job_id": job.id, "job_url": job.url},
    )
    update_job_fields(db, job.id, {
        "cv_generated": True,
        "cv_path": result["tex_path"],
    })
    if is_firestore_handle(db):
        from app.services.job_service import register_cv_version

        register_cv_version(db, job.id, {
            "tex_path": result["tex_path"],
            "pdf_path": result.get("pdf_path"),
            "match_score": score,
            "skills_selected": content.skills
            if hasattr(content, "skills") else [],
        })

    return {
        "job_id": job.id,
        "match_score": score,
        "decision": decision,
        "provider": generated.get("provider"),
        "reference_cvs_used": [r["profile_id"] for r in references],
        "cv_generated": True,
        "tex_path": result["tex_path"],
        "pdf_path": result["pdf_path"],
        "pdf_ok": result["pdf_ok"],
        "download_tex": f"/jobs/{job.id}/cv/download?format=tex",
        "download_pdf": (
            f"/jobs/{job.id}/cv/download?format=pdf"
            if result["pdf_ok"]
            else None
        ),
    }


@app.get("/jobs/{job_id}/cv")
def get_job_cv(job_id: str, db: Session = Depends(get_db)):
    """Estado del CV asociado a la oferta."""
    from pathlib import Path

    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    tex_path = job.cv_path
    pdf_path = (
        str(Path(tex_path).with_suffix(".pdf"))
        if tex_path and Path(tex_path).with_suffix(".pdf").exists()
        else None
    )
    return {
        "job_id": job.id,
        "match_score": job.match_score,
        "cv_generated": bool(job.cv_generated),
        "tex_path": tex_path,
        "pdf_path": pdf_path,
        "download_tex": (
            f"/jobs/{job.id}/cv/download?format=tex" if tex_path else None
        ),
        "download_pdf": (
            f"/jobs/{job.id}/cv/download?format=pdf" if pdf_path else None
        ),
    }


@app.get("/jobs/{job_id}/customized-cv")
def get_customized_cv(job_id: str, db: Session = Depends(get_db)):
    """CV personalizado de la oferta sin consumir IA.

    Estados: NOT_GENERATED (nunca se genero) | READY (reutiliza el
    existente) | ERROR (marcado como generado pero archivos ausentes).
    Generar = POST /jobs/{job_id}/cv. Regenerar = POST de nuevo.
    """
    from app.services.job_service import get_customized_cv as assemble

    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    customized = assemble(db, job_id)
    if customized is None:
        return {
            "state": "NOT_GENERATED",
            "job_id": job.id,
            "hint": "Genera con POST /jobs/{id}/cv (respeta umbrales).",
        }
    return customized


@app.get("/jobs/{job_id}/cv/download")
def download_job_cv(
    job_id: str,
    format: str = Query("pdf", pattern="^(pdf|tex)$"),
    db: Session = Depends(get_db),
):
    """Descarga el CV generado (pdf o tex)."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    job = get_job_by_id(db=db, job_id=job_id)
    if not job or not job.cv_generated or not job.cv_path:
        raise HTTPException(
            status_code=404, detail="Esta oferta no tiene CV generado."
        )
    tex = Path(job.cv_path)
    target = tex.with_suffix(".pdf") if format == "pdf" else tex
    # El path viene de la BD: confinarlo bajo CVS_DIR (anti traversal).
    from app.config import CVS_DIR

    try:
        target.resolve().relative_to(CVS_DIR.resolve())
    except ValueError:
        raise HTTPException(
            status_code=404, detail="Archivo no disponible."
        )
    if not target.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Archivo {format} no disponible"
            + (
                " (pdflatex no instalado: solo existe el .tex)"
                if format == "pdf"
                else ""
            ),
        )
    from app.services.job_service import log_interaction

    log_interaction(db, "CV_DOWNLOADED", job.id, None, {"format": format})
    return FileResponse(
        path=str(target),
        filename=f"cv_job_{job.id}.{format}",
    )


@app.patch("/jobs/{job_id}/status", response_model=JobResponse)
def patch_job_status(
    job_id: str, payload: JobStatusUpdate, db: Session = Depends(get_db)
):
    """Conservar / descartar / recuperar / marcar abierta o postulada."""
    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    try:
        return update_job_status(
            db=db,
            job=job,
            status=payload.status,
            discard_reason=payload.discard_reason,
            discard_note=payload.discard_note,
            application_status=payload.application_status,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/applications")
def list_applications_endpoint(
    limit: int = 200, db: Session = Depends(get_db)
):
    """Postulaciones con eventos. En sqlite se derivan de ofertas
    aplicadas (compatibilidad); en Firestore leen la coleccion."""
    from app.services.job_service import list_applications

    return list_applications(db, limit=limit)


@app.get("/applications/{app_id}")
def get_application_endpoint(app_id: str, db: Session = Depends(get_db)):
    """Una postulacion con su linea de tiempo (solo Firestore; en
    sqlite las postulaciones viven en la oferta aplicada)."""
    from app.services.job_service import get_application

    application = get_application(db, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Postulacion no encontrada.")
    return application


@app.get("/jobs/{job_id}/detail")
def get_job_detail(job_id: str, db: Session = Depends(get_db)):
    """Trae la descripcion completa de una oferta guardada."""
    from app.services.job_service import log_interaction
    from app.services.job_service import update_job_fields

    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")

    if job.description:
        from app.services.job_service import register_job_view

        log_interaction(db, "JOB_VIEWED", job.id)
        register_job_view(db, job)
        return {
            "id": job.id,
            "title": job.title,
            "url": job.url,
            "description": job.description,
            "cached": True,
        }

    try:
        detail = get_scraper(job.source or "computrabajo").get_job_detail(
            job.url
        )
    except Exception as error:  # noqa: BLE001
        message = str(error)
        if "404" in message or "expir" in message.lower():
            raise HTTPException(
                status_code=404,
                detail="La oferta original ya no está disponible "
                "(expiró o fue eliminada en la fuente).",
            )
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando el detalle: {error}",
        )

    job.description = detail.get("description", "")
    # La pagina de detalle suele traer la fecha exacta (datePosted,
    # publishDate); guardala si la oferta aun no la tiene.
    detail_fields: dict = {"description": detail.get("description", "")}
    if detail.get("published_at") and not job.published_at:
        detail_fields["published_at"] = detail["published_at"]
        detail_fields["published_text"] = detail.get("published_text") or ""
    from app.services.job_service import log_interaction
    from app.services.job_service import register_job_view
    from app.services.job_service import update_job_fields

    job = update_job_fields(db, job.id, detail_fields)
    log_interaction(db, "JOB_VIEWED", job.id)
    register_job_view(db, job)

    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "url": job.url,
        "description": job.description,
        "tags": detail.get("tags", []),
        "requirements": detail.get("requirements", []),
        "skills": detail.get("skills", []),
        "cached": False,
    }
