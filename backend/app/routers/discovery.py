"""Router discovery (Fase 1: extraido de app/main.py sin cambios de logica)."""
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
@router.get("/discovery/packs")
def discovery_packs():
    """Capas de busqueda disponibles (titulos, habilidades,
    responsabilidades) para POST /jobs/discover."""
    from app.analysis.discovery import PACKS

    return {
        "packs": {name: queries for name, queries in PACKS.items()},
        "counts": {name: len(queries) for name, queries in PACKS.items()},
    }


@router.post("/jobs/discover")
def discover_jobs(
    payload: dict[str, Any],
    request: Request,
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
        uid, email = _profile_identity(request)
        return discover(
            db,
            source=source,
            packs=list(packs),
            queries=list(queries) if queries else None,
            pages=pages,
            max_details=max_details,
            uid=uid,
            email=email,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Error en descubrimiento: {error}"
        )


@router.post("/jobs/analyze-pending")
def analyze_pending_endpoint(
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
):
    """Analiza en lote filas con descripcion pero sin score."""
    limit = int((payload or {}).get("limit", 50))
    return analyze_pending(db, limit=limit)


@router.get("/jobs/search")
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
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not q.strip():
        raise HTTPException(
            status_code=400, detail="La consulta no puede estar vacia."
        )

    from app.services import search_orchestrator as orch

    try:
        scraper = orch.resolve_scraper(source)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    try:
        jobs = orch.scrape_with(
            scraper, source, q, max_pages=pages,
            include_details=details, location=location,
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
    found_total = len(jobs)
    jobs = orch.filter_by_age(jobs, max_age_days)
    aged_out = found_total - len(jobs)

    # Ajuste a la configuracion de busqueda (jerarquia perfil >
    # global): solo descarta ante contradiccion explicita en
    # titulo/descripcion; sin dato la oferta pasa al analisis.
    from app.services.search_config import resolve_for_request

    uid, email = _profile_identity(request)
    fit_config = resolve_for_request(db, uid)
    jobs, fit_filtered = orch.filter_by_fit(jobs, fit_config)

    saved_jobs = orch.save_batch(
        db, jobs, search_query=q, uid=uid, email=email)

    # Analisis despues del scraping (no solo mostrar resultados):
    # trae detalle donde falta, clasifica rol por contenido y persiste
    # match_score/matching/missing/evidence (mismo pipeline que discover).
    analyzed = 0
    relevant = 0
    details_fetched = 0
    if analyze and saved_jobs:
        from app.services.job_service import get_profile

        stats = orch.analyze_batch(
            db,
            scraper=scraper,
            profile=get_profile(db, uid=uid, email=email),
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
        "filtered_out": aged_out,
        "fit_filtered": fit_filtered,
        "fit_config": {k: v for k, v in fit_config.items()},
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


@router.get("/jobs/search/stream")
def search_jobs_stream(
    q: str = Query(..., min_length=2, description="Ej: desarrollador python"),
    pages: int = Query(1, ge=1, le=10),
    source: str = Query(
        "computrabajo", description="Fuente: computrabajo | magneto | ..."
    ),
    analyze: bool = Query(
        True,
        description="Analizar ofertas al final (match_score, "
        "detected_role, evidence).",
    ),
    max_details: int = Query(
        10, ge=0, le=30, description="Detalles a traer para ofertas sin descripcion"
    ),
    location: str | None = Query(
        None,
        description="Filtrar por ciudad antes de guardar.",
    ),
    max_age_days: int = Query(
        0, ge=0, le=60,
        description="Antigüedad maxima en dias (0 = todas).",
    ),
    # Token de autenticación como query param (EventSource no soporta headers)
    token: str | None = Query(None, description="Firebase ID token para autenticación"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """Busqueda progresiva (Server-Sent Events): emite las ofertas a
    medida que cada pagina se scrapea y guarda, sin esperar al final.

    Eventos: started, jobs{page, jobs[]}, analyzing, done{...}, error.
    El scraping corre en un hilo con su propia sesion de BD; al
    cerrar el cliente se deja de emitir (lo ya guardado persiste).
    Misma deduplicacion y filtros que GET /jobs/search.
    """
    import json as _json
    import queue
    import threading

    from fastapi.responses import StreamingResponse

    from app.services import search_orchestrator as orch

    if not q.strip():
        raise HTTPException(
            status_code=400, detail="La consulta no puede estar vacia."
        )
    try:
        scraper = orch.resolve_scraper(source)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    # Obtener uid/email desde el token en query param (EventSource no soporta headers)
    uid = None
    email = None
    if token:
        try:
            from app.auth import verify_bearer_token
            claims = verify_bearer_token(f"Bearer {token}")
            uid = claims.get("uid")
            email = claims.get("email")
        except HTTPException:
            pass  # Token inválido, continuar sin auth

    # Cola de eventos entre el hilo de scraping y el generador SSE.
    # Sin esto el stream abortaba tras "started" (NameError) y el
    # frontend solo veia "Se perdio la conexion...".
    events: queue.Queue = queue.Queue()

    # Ajuste global del usuario (sin perfil aqui): se resuelve una vez
    # con la sesion del request; el worker la reutiliza por lote.
    from app.services.search_config import resolve_for_request

    stream_fit = resolve_for_request(db, uid)
    fit_discarded: dict = {}

    def _worker() -> None:
        from app.scheduler import _close_db
        from app.scheduler import _new_db

        handle, needs_close = _new_db()
        try:
            def on_page(jobs: list, page: int) -> None:
                try:
                    batch = orch.filter_batch(jobs, location, max_age_days)
                    batch, _fit = orch.filter_by_fit(batch, stream_fit)
                    for reason, count in _fit.items():
                        fit_discarded[reason] = fit_discarded.get(
                            reason, 0) + count
                    saved = orch.save_batch(
                        db=handle, jobs=batch, search_query=q,
                        uid=uid, email=email)
                except Exception:
                    # Una pagina con datos malos no debe abortar toda la
                    # busqueda: se salta el lote y sigue con la siguiente.
                    return
                try:
                    events.put(("jobs", {
                        "page": page,
                        "jobs": [
                            {"id": job.id, "title": job.title,
                             "company": job.company,
                             "location": job.location, "url": job.url,
                             "source": job.source}
                            for job in saved
                        ],
                    }))
                except Exception:
                    pass

            found = orch.scrape_with(
                scraper, source, q, max_pages=pages,
                include_details=False, location=location, on_page=on_page)
            events.put(("finished", {"found": len(found)}))
        except Exception as error:  # noqa: BLE001
            events.put(("error", str(error)[:300]))
        finally:
            _close_db(handle, needs_close)

    def _event(payload: dict) -> str:
        return f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"

    def gen():
        yield _event({"type": "started", "query": q, "pages": pages,
                      "source": source, "location": location,
                      "max_age_days": max_age_days})
        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        saved_ids: list[str] = []
        found_total = 0
        while True:
            try:
                kind, payload = events.get(timeout=15)
            except queue.Empty:
                yield ": ping\n\n"
                if not thread.is_alive():
                    yield _event({"type": "error", "message":
                                  "Busqueda interrumpida."})
                    return
                continue
            if kind == "jobs":
                for job in payload.get("jobs", []):
                    if job.get("id") not in saved_ids:
                        saved_ids.append(job["id"])
                yield _event({"type": "jobs", **payload})
            elif kind == "finished":
                found_total = int(payload.get("found", 0))
                break
            elif kind == "error":
                yield _event({"type": "error",
                              "message": payload})
                return
        analyzed = 0
        relevant = 0
        details_fetched = 0
        if analyze and saved_ids:
            yield _event({"type": "analyzing",
                          "count": len(saved_ids)})
            try:
                from app.services.job_service import get_jobs_by_ids
                from app.services.job_service import get_profile

                rows = get_jobs_by_ids(db, saved_ids)
                stats = orch.analyze_batch(
                    db, scraper=scraper, profile=get_profile(db, uid=uid, email=email),
                    rows=rows, max_details=max_details, delay=0)
                analyzed = stats["analyzed"]
                relevant = stats["relevant"]
                details_fetched = stats["details_fetched"]
            except Exception as error:  # noqa: BLE001
                # El analisis no debe invalidar lo ya guardado: se cierra
                # con done parcial en vez de error para que el frontend
                # muestre las ofertas en lugar de "conexion perdida".
                yield _event({"type": "done", "query": q, "pages": pages,
                              "source": source, "location": location,
                              "max_age_days": max_age_days, "found": found_total,
                              "saved_unique": len(saved_ids), "analyzed": 0,
                              "relevant": 0, "details_fetched": 0,
                              "fit_filtered": dict(fit_discarded),
                              "analysis_error": str(error)[:200]})
                return
        yield _event({"type": "done", "query": q, "pages": pages,
                      "source": source, "location": location,
                      "max_age_days": max_age_days, "found": found_total,
                      "saved_unique": len(saved_ids), "analyzed": analyzed,
                      "relevant": relevant,
                      "details_fetched": details_fetched,
                      "fit_filtered": dict(fit_discarded)})

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


