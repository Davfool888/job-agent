"""Router jobs (Fase 1: extraido de app/main.py sin cambios de logica)."""
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


def _validate_provider(provider: str | None) -> None:
    """400 si el id no es un proveedor soportado (None = auto)."""
    if not provider:
        return
    from app.ai.user_providers import SUPPORTED

    if provider not in SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Proveedor desconocido: {provider}. Soportados: "
                   f"{', '.join(sorted(SUPPORTED))}.")

router = APIRouter()
@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    limit: int = 200,
    status: str | None = None,
    since: str | None = Query(
        None,
        description="Solo ofertas con found_at (o created_at) posterior a "
        "esta fecha ISO. Ej: 2026-09-30T10:00:00",
    ),
    request: Request = None,
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
    uid, email = _profile_identity(request)
    return get_all_jobs(db=db, limit=limit, status=status, since=since_dt, uid=uid, email=email)


@router.post("/jobs/{job_id}/analyze")
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
            detail = registry.get_scraper(job.source or "computrabajo").get_job_detail(
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
    try:
        from app.analysis.verdict import build_fit_report

        result["fit_report"] = build_fit_report(
            {"title": job.title or "",
             "description": job.description or ""},
            result, get_profile(db))
    except Exception:  # noqa: BLE001
        pass
    return {
        "job": JobResponse.model_validate(job).model_dump(),
        "analysis": result,
    }


@router.post("/jobs/{job_id}/tailor")
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


@router.post("/jobs/{job_id}/adapt-cv")
def adapt_job_cv(job_id: str, request: Request, db: Session = Depends(get_db),
                 token: str | None = Query(None),
                 provider: str | None = Query(
                     None, description="Proveedor IA propio (ver /ai-keys/status); vacio = auto")):
    """Adaptar-perfil: matching deterministico + seleccion + HTML/CSS
    + PDF (Chromium) con el perfil ficticio de invitado. Sin LaTeX,
    sin LLM obligatorio. Errores controlados {success, error}."""
    from fastapi.responses import JSONResponse

    from app.adapt.service import adapt_profile_for_job, AdaptError, error_body

    # UID+email de la sesion (invitado = demo, Google = su perfil).
    uid, email = _adapt_identity(request, token)
    _validate_provider(provider)

    try:
        return adapt_profile_for_job(db, job_id, uid, email, provider)
    except AdaptError as error:
        return JSONResponse(
            status_code=error.http, content=error_body(error))
    except Exception as error:  # noqa: BLE001
        # Nunca 500 crudo: el frontend espera {success, error}.
        return JSONResponse(status_code=502, content={
            "success": False, "error": {
                "code": "UNKNOWN_ERROR",
                "message": f"Fallo inesperado: {error}"[:300]}})


@router.post("/jobs/{job_id}/adapt-cv/start", status_code=202)
def start_adapt_job_cv(job_id: str, request: Request, db: Session = Depends(get_db),
                       token: str | None = Query(None),
                       provider: str | None = Query(
                           None, description="Proveedor IA propio (ver /ai-keys/status); vacio = auto")):
    """Inicia la adaptacion en segundo plano. Responde 202 de inmediato
    (valida job + perfil sin Chromium); el cliente hace polling a
    GET /jobs/{job_id}/adapt-cv/status hasta done/error y luego descarga
    el PDF. Evita el timeout del flujo sync en instancias gratuitas."""
    from fastapi.responses import JSONResponse

    from app.adapt.jobs import prevalidate_adapt_job, start_adapt_job
    from app.adapt.service import AdaptError, error_body

    uid, email = _adapt_identity(request, token)
    _validate_provider(provider)

    try:
        prevalidate_adapt_job(db, job_id, uid, email)
    except AdaptError as error:
        return JSONResponse(
            status_code=error.http, content=error_body(error))
    body = start_adapt_job(job_id, uid, email, provider)
    return JSONResponse(status_code=202, content=body)


@router.get("/jobs/{job_id}/adapt-cv/status")
def adapt_job_cv_status(
    job_id: str, request: Request, db: Session = Depends(get_db),
    token: str | None = Query(None),
):
    """Estado para polling: idle | processing | done (+result) | error
    (+error {code, message}). done incluye download_url del PDF."""
    from fastapi.responses import JSONResponse

    from app.adapt.jobs import get_adapt_status
    from app.adapt.service import AdaptError

    uid, email = _adapt_identity(request, token)
    try:
        return get_adapt_status(db, job_id, uid, email)
    except AdaptError as error:
        return JSONResponse(
            status_code=error.http,
            content={"success": False,
                     "error": {"code": error.code,
                               "message": str(error)}})


@router.get("/jobs/{job_id}/adapt-cv/download")
def download_adapt_cv(
    job_id: str,
    format: str = Query("pdf", pattern="^(pdf|html)$"),
    token: str | None = Query(
        None, description="Firebase ID token (el iframe no envia headers)"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Descarga el CV adaptado (pdf o html) DEL USUARIO de la sesion.
    404 honesto si no existe.

    Si la oferta existe pero el archivo se perdio (reinicio con disco
    efimero), se regenera al vuelo con EL PERFIL DE LA SESION antes
    de servir. Como fallback se acepta el archivo legacy (sin
    subdirectorio de usuario) generado antes del aislamiento."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.adapt.service import adapt_dir, legacy_adapt_dir
    from app.services.job_service import get_job_by_id

    uid, email = _adapt_identity(request, token)
    job = None
    try:
        job = get_job_by_id(db=db, job_id=job_id)
    except (TypeError, ValueError):
        job = None
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    from app.config import ADAPT_CVS_DIR

    target = adapt_dir(job.id, uid, email) / (f"cv.{format}")
    try:
        target.resolve().relative_to(ADAPT_CVS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Archivo no disponible.")
    if not Path(target).exists():
        # El archivo legacy (sin subdirectorio) solo lo puede reclamar
        # el invitado: a un usuario autenticado NUNCA se le sirve el
        # archivo de otro (ni el demo). Se le regenera el suyo.
        if uid is None:
            legacy = legacy_adapt_dir(job.id) / (f"cv.{format}")
            if Path(legacy).exists():
                target = legacy
    if not Path(target).exists():
        # Disco efimero: la oferta existe pero el archivo se perdio.
        # Regenerar es mas util que un 404.
        from fastapi.responses import JSONResponse

        from app.adapt.service import adapt_profile_for_job, AdaptError

        try:
            adapt_profile_for_job(db, job.id, uid, email)
        except AdaptError as error:
            return JSONResponse(
                status_code=error.http,
                content={"success": False,
                         "error": {"code": error.code,
                                   "message": str(error)}},
            )
        if not Path(target).exists():
            raise HTTPException(
                status_code=404,
                detail="Aún no hay CV adaptado. Usa «Adaptar perfil».",
            )
    # Puerta de entrega: si la ultima auditoria tiene bloqueantes, el
    # PDF no se entrega como valido (se regenera via Adaptar perfil).
    if format == "pdf":
        from app.adapt.audit import blocking_issues as _blocking

        try:
            import json as _json

            sibling = Path(target).parent / "adapt.json"
            if sibling.exists():
                _audit = _json.loads(
                    sibling.read_text(encoding="utf-8")).get("audit") or {}
                _blocking_issues = _blocking(_audit)
                if _blocking_issues:
                    raise HTTPException(
                        status_code=409,
                        detail="El ultimo CV generado no paso la auditoria "
                        "(" + "; ".join(
                            i["message"] for i in _blocking_issues[:2]) +
                        "). Regeneralo con «Adaptar perfil».",
                    )
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            pass
    # Para PDF: inline para visualizar en iframe; para HTML: inline también
    # El parámetro content_disposition_type controla si descarga (attachment) o muestra (inline)
    return FileResponse(
        path=str(target),
        filename=f"cv_adaptado_job_{job.id}.{format}",
        media_type="application/pdf" if format == "pdf" else "text/html",
        content_disposition_type="inline",
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    from app.services.job_service import can_view_job
    uid, email = _profile_identity(request)
    if not can_view_job(db, job_id, uid, email):
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    return job


@router.get("/jobs/{job_id}/analysis")
def get_job_analysis(job_id: str, request: Request, db: Session = Depends(get_db)):
    """Analisis estructurado guardado (§5, §14)."""
    from app.services.job_service import can_view_job
    uid, email = _profile_identity(request)
    if not can_view_job(db, job_id, uid, email):
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    analysis = {
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
    try:
        from app.analysis.verdict import build_fit_report
        from app.services.job_service import get_profile_for
        from app.services.job_service import get_rich_profile_for

        flat = get_profile_for(db, uid, email)
        rich = get_rich_profile_for(db, uid, email)
        analysis["fit_report"] = build_fit_report(
            {"title": job.title or "", "description": job.description or "",
             "requirements": job.requirements or "",
             "responsibilities": job.responsibilities or ""},
            {"match_score": job.match_score,
             "matched_skills": analysis["matching_skills"],
             "missing_skills": analysis["missing_skills"],
             "experience_required": job.experience_required,
             "category": job.category,
             "detected_role": job.detected_role,
             "score_breakdown": getattr(job, "score_breakdown", None)},
            flat, rich)
    except Exception:  # noqa: BLE001
        pass
    return analysis


@router.post("/jobs/{job_id}/cv")
def generate_job_cv(
    job_id: str,
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    request: Request = None,
    provider: str | None = Query(
        None, description="Proveedor IA propio (ver /ai-keys/status); vacio = auto"),
):
    """Genera CV para la oferta (§10-§13): respeta umbrales salvo
    force=true. Estructura: data/cvs/job_<ID>/{analysis.json,
    cv_content.json, cv.tex, cv.pdf?}."""
    from app.agents.cv_agent import CVAgent
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
    # Cuota del usuario, nunca global: con keys se usa su proveedor
    # (elegido o primero disponible con fallback); sin keys, flujo
    # deterministico local.
    from app.ai import user_llm

    _validate_provider(provider)
    uid, email = _profile_identity(request) if request is not None else (None, None)
    user_client = user_llm.for_user(db, uid, provider)
    try:
        if user_client is not None:
            generated = user_llm.generate_cv_content_for_user(
                user_client, job_dict, analysis, profile,
                references or None)
        else:
            from app.ai.providers.rule_based import RuleBasedProvider

            generated = RuleBasedProvider().generate_cv_content(
                job_dict, analysis, profile, references or None)
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


@router.get("/jobs/{job_id}/cv")
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


@router.get("/jobs/{job_id}/customized-cv")
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


@router.get("/jobs/{job_id}/cv/download")
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
    # Para PDF: inline para visualizar en iframe/navegador; para TEX: attachment (descarga)
    return FileResponse(
        path=str(target),
        filename=f"cv_job_{job.id}.{format}",
        media_type="application/pdf" if format == "pdf" else "text/x-tex",
        content_disposition_type="inline" if format == "pdf" else "attachment",
    )


@router.patch("/jobs/{job_id}/status", response_model=JobResponse)
def patch_job_status(
    job_id: str, payload: JobStatusUpdate, request: Request, db: Session = Depends(get_db)
):
    """Conservar / descartar / recuperar / marcar abierta o postulada."""
    from app.services.job_service import can_view_job
    uid, email = _profile_identity(request)
    if not can_view_job(db, job_id, uid, email):
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
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


@router.get("/applications")
def list_applications_endpoint(
    request: Request = None, limit: int = 200, db: Session = Depends(get_db)
):
    """Postulaciones con eventos. En sqlite se derivan de ofertas
    aplicadas (compatibilidad); en Firestore leen la coleccion."""
    from app.services.job_service import list_applications
    uid, email = _profile_identity(request)
    return list_applications(db, limit=limit, uid=uid)


@router.get("/applications/{app_id}")
def get_application_endpoint(app_id: str, db: Session = Depends(get_db)):
    """Una postulacion con su linea de tiempo (solo Firestore; en
    sqlite las postulaciones viven en la oferta aplicada)."""
    from app.services.job_service import get_application

    application = get_application(db, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Postulacion no encontrada.")
    return application


@router.get("/jobs/{job_id}/detail")
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
        detail = registry.get_scraper(job.source or "computrabajo").get_job_detail(
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


