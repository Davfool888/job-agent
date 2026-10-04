"""Descubrimiento por capas (§3-§5 del requerimiento).

Capa 1 (titulos) + Capa 2 (habilidades) + Capa 3 (responsabilidades):
cada query se ejecuta contra el scraper de la fuente elegida y los
resultados se guardan con `discovered_by = [slug de la query]`.

Dedup (§16): por URL (save_jobs) + por huella titulo+empresa+ubicacion
(fingerprint). Una oferta encontrada por "Power BI" y luego por
"Analista de Datos" genera UN solo registro con discovered_by =
["power-bi", "analista-de-datos"].

Capa 4 (analisis completo, §6): para filas sin descripcion se trae el
detalle, priorizando las que ya muestran señales en titulo/snippet
(arquitectura hibrida §19-§20: reglas baratas primero, IA solo para
casos ambiguos — el hook IA queda documentado en agents/job_analyzer).
"""
from __future__ import annotations

import logging
import time

from app.analysis.scorer import analyze_job
from app.scraper.base import slugify_query
from app.services import job_service as jobs

logger = logging.getLogger(__name__)

TITLE_QUERIES = [
    "analista de datos",
    "analista datos",
    "data analyst",
    "data analytics",
    "analista BI",
    "BI analyst",
    "business intelligence",
    "ingeniero de datos",
    "data engineer",
    "cientifico de datos",
    "data scientist",
    "especialista de datos",
    "auxiliar de datos",
    "tecnico de datos",
    "profesional de datos",
    "python developer",
    "desarrollador python",
    "programador python",
    "backend python",
    "Power BI",
    "inteligencia de negocios",
    "analista SQL",
    "bases de datos",
    "analista de informacion",
]

SKILL_QUERIES = [
    "Power BI",
    "Excel avanzado",
    "SQL",
    "Python",
    "Pandas",
    "ETL",
    "limpieza de datos",
    "bases de datos",
    "visualizacion de datos",
    "dashboards",
    "indicadores",
    "KPIs",
    "automatizacion",
    "Power Query",
    "DAX",
]

RESPONSIBILITY_QUERIES = [
    "analizar informacion",
    "analizar datos",
    "limpiar datos",
    "generar reportes",
    "elaborar indicadores",
    "crear dashboards",
    "consolidar informacion",
    "automatizar reportes",
    "generar informes",
    "analisis de bases de datos",
]

PACKS: dict[str, list[str]] = {
    "titles": TITLE_QUERIES,
    "skills": SKILL_QUERIES,
    "responsibilities": RESPONSIBILITY_QUERIES,
}


def _has_prefilter_signal(job: dict) -> bool:
    """Compat: el discovery agent usa prefilter.prefilter_signals."""
    from app.analysis.prefilter import deserves_deep_analysis

    return deserves_deep_analysis(job)


def _tag_discovered(db, job_ids: list, slug: str) -> None:
    """Compat: delega en job_service.tag_discovered (mismo comportamiento
    en ambos motores)."""
    from app.services.job_service import tag_discovered

    tag_discovered(db, job_ids, slug)


def enrich_and_analyze(
    db: Session,
    *,
    scraper,
    profile: dict,
    rows: list,
    max_details: int = 10,
    delay: float = 1.0,
    uid: str | None = None,
    email: str | None = None,
) -> dict:
    """Capa 4 reutilizable: trae detalle donde falta (priorizando
    señales baratas), analiza titulo+descripcion+requisitos contra el
    perfil y persiste match_score/detected_role/evidence. Lo usan
    `discover()` y `GET /jobs/search` para no duplicar logica."""
    candidates = [r for r in rows if not (r.description or "").strip()]
    with_signal = [
        j
        for j in candidates
        if _has_prefilter_signal(
            {"title": j.title, "description": j.description or ""}
        )
    ]
    without = [j for j in candidates if j not in with_signal]
    ordered = (with_signal + without)[: max(0, max_details)]

    details_ok = 0
    for row in ordered:
        try:
            detail = scraper.get_job_detail(row.url)
            if detail.get("description"):
                jobs.update_job_fields(
                    db, row.id, {"description": detail["description"]}
                )
                details_ok += 1
        except Exception as error:  # noqa: BLE001
            logger.warning("Detalle fallo %s: %s", row.url, error)
        time.sleep(delay)

    # Releer: las descripciones recien traidas deben entrar al analisis.
    if details_ok:
        rows = jobs.get_jobs_by_ids(db, [row.id for row in rows])

    analyzed = 0
    relevant = 0
    for row in rows:
        if not (row.title or row.description):
            continue
        result = analyze_job(
            {
                "title": row.title or "",
                "description": row.description or "",
                "requirements": row.requirements or "",
                "responsibilities": row.responsibilities or "",
            },
            profile,
        )
        jobs.save_analysis(
            db,
            row,
            match_score=result["match_score"],
            matched=result["matched_skills"],
            missing=result["missing_skills"],
            detected_role=result["detected_role"],
            category=result["category"],
            evidence=result["evidence"],
            experience=result["experience_required"],
        )
        analyzed += 1
        if result["match_score"] >= 40 or result["category"] != "OTHER":
            relevant += 1

    return {
        "details_fetched": details_ok,
        "analyzed": analyzed,
        "relevant": relevant,
    }


def discover(
    db: Session,
    source: str = "computrabajo",
    packs: list[str] | None = None,
    queries: list[str] | None = None,
    pages: int = 1,
    max_details: int = 15,
    delay: float = 1.0,
    uid: str | None = None,
    email: str | None = None,
) -> dict:
    """Ejecuta descubrimiento por capas y devuelve resumen honesto."""
    from app.scraper.registry import get_scraper

    if queries is not None:
        selected = [q for q in queries if q.strip()]
        if not selected:
            raise ValueError(
                "Indica al menos una consulta (ej: abogado junior)."
            )
    else:
        selected_packs = packs or ["titles", "skills", "responsibilities"]
        selected = []
        for pack in selected_packs:
            if pack not in PACKS:
                raise ValueError(
                    f"Pack desconocido: {pack}. "
                    f"Disponibles: {', '.join(PACKS)}"
                )
            selected.extend(PACKS[pack])

    scraper = get_scraper(source)
    profile = jobs.get_profile(db)

    per_query: list[dict] = []
    all_ids: set[int] = set()
    errors: list[dict] = []

    for query in selected:
        slug = slugify_query(query)
        try:
            found = scraper.search(query, max_pages=pages)
        except Exception as error:  # noqa: BLE001
            errors.append({"query": query, "error": str(error)[:200]})
            logger.warning("Discovery fallo query %r: %s", query, error)
            continue
        saved = jobs.save_jobs(db, found, search_query=query, uid=uid, email=email)
        ids = [job.id for job in saved]
        _tag_discovered(db, ids, slug)
        all_ids.update(ids)
        per_query.append(
            {"query": query, "found": len(found), "saved": len(saved)}
        )
        time.sleep(delay)

    # Capa 4: detalle + analisis via helper compartido (tambien lo
    # usa GET /jobs/search para analizar despues del scraping).
    rows = jobs.get_jobs_by_ids(db, list(all_ids)) if all_ids else []
    stats = enrich_and_analyze(
        db,
        scraper=scraper,
        profile=profile,
        rows=rows,
        max_details=max_details,
        delay=delay,
        uid=uid,
        email=email,
    )
    analyzed = stats["analyzed"]
    relevant = stats["relevant"]
    details_ok = stats["details_fetched"]

    return {
        "source": scraper.source,
        "packs": packs or ["custom"],
        "queries_run": len(per_query),
        "queries_failed": len(errors),
        "found": sum(q["found"] for q in per_query),
        "saved_unique": len(all_ids),
        "details_fetched": details_ok,
        "analyzed": analyzed,
        "relevant": relevant,
        "per_query": per_query,
        "errors": errors,
    }
