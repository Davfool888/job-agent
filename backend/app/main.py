from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
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
from app.schemas.job import JobResponse
from app.schemas.job import JobStatusUpdate
from app.scraper.registry import available_sources
from app.scraper.registry import get_scraper
from app.services.job_service import analyze_pending
from app.services.job_service import backfill_fingerprints
from app.services.job_service import get_all_jobs
from app.services.job_service import get_job_by_id
from app.services.job_service import get_profile
from app.services.job_service import get_stats
from app.services.job_service import save_analysis
from app.services.job_service import save_jobs
from app.services.job_service import save_profile
from app.services.job_service import update_job_status


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_columns()
    db = SessionLocal()
    try:
        backfill_fingerprints(db)
    finally:
        db.close()
    yield


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


@app.get("/profile")
def read_profile(db: Session = Depends(get_db)):
    return get_profile(db)


@app.put("/profile")
def write_profile(payload: dict[str, Any], db: Session = Depends(get_db)):
    return save_profile(db, payload or {})


@app.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    limit: int = 200,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    if status and status not in JOB_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Estado invalido. Permitidos: {', '.join(JOB_STATUSES)}",
        )
    return get_all_jobs(db=db, limit=limit, status=status)


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
    pages = int(payload.get("pages") or 1)
    max_details = int(payload.get("max_details", 15))
    if isinstance(packs, str):
        packs = [packs]
    try:
        return discover(
            db,
            source=source,
            packs=list(packs),
            queries=list(queries) if queries else None,
            pages=max(1, min(pages, 5)),
            max_details=max(0, min(max_details, 60)),
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
def analyze_job_endpoint(job_id: int, db: Session = Depends(get_db)):
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
                job.description = detail["description"]
                db.add(job)
                db.commit()
        except Exception as error:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"No se pudo traer el detalle: {error}",
            )

    result = JobAnalyzer().analyze(
        {"title": job.title or "", "description": job.description or ""},
        get_profile(db),
    )
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
    db.refresh(job)
    return {
        "job": JobResponse.model_validate(job).model_dump(),
        "analysis": result,
    }



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
        jobs = scraper.search(q, max_pages=pages, include_details=details)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando {scraper.source}: {error}",
        )

    saved_jobs = save_jobs(db=db, jobs=jobs, search_query=q)

    return {
        "query": q,
        "pages": pages,
        "source": scraper.source,
        "found": len(jobs),
        "saved": len(saved_jobs),
        "jobs": [
            {
                "id": job.id,
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "url": job.url,
                "source": job.source,
                "description": job.description,
            }
            for job in saved_jobs
        ],
    }


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")
    return job


@app.get("/jobs/{job_id}/analysis")
def get_job_analysis(job_id: int, db: Session = Depends(get_db)):
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
    job_id: int,
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
    try:
        generated = get_router().generate_cv_content(
            job_dict, analysis, profile
        )
        content = CVContent.model_validate(generated)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Ningun proveedor genero el CV: {error}"
        )

    personal = profile.get("personal", {}) or {}
    result = cvgen.generate_for_job(
        job.id,
        content,
        personal,
        analysis={**analysis, "job_id": job.id, "job_url": job.url},
    )
    job.cv_generated = 1
    job.cv_path = result["tex_path"]
    db.add(job)
    db.commit()

    return {
        "job_id": job.id,
        "match_score": score,
        "decision": decision,
        "provider": generated.get("provider"),
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
def get_job_cv(job_id: int, db: Session = Depends(get_db)):
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


@app.get("/jobs/{job_id}/cv/download")
def download_job_cv(
    job_id: int,
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
    return FileResponse(
        path=str(target),
        filename=f"cv_job_{job.id}.{format}",
    )


@app.patch("/jobs/{job_id}/status", response_model=JobResponse)
def patch_job_status(
    job_id: int, payload: JobStatusUpdate, db: Session = Depends(get_db)
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


@app.get("/jobs/{job_id}/detail")
def get_job_detail(job_id: int, db: Session = Depends(get_db)):
    """Trae la descripcion completa de una oferta guardada."""
    job = get_job_by_id(db=db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Oferta no encontrada.")

    if job.description:
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
        raise HTTPException(
            status_code=502,
            detail=f"Error consultando el detalle: {error}",
        )

    job.description = detail.get("description", "")
    # La pagina de detalle suele traer la fecha exacta (datePosted,
    # publishDate); guardala si la oferta aun no la tiene.
    if detail.get("published_at") and not job.published_at:
        job.published_at = detail["published_at"]
        job.published_text = detail.get("published_text") or ""
    db.add(job)
    db.commit()
    db.refresh(job)

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
