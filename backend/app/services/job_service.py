from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import JOB_STATUSES
from app.database.models import Job
from app.database.models import Profile
from app.scraper.base import fingerprint_of
from app.scraper.normalize import content_hash_of
from app.scraper.normalize import normalize_job


DEFAULT_PROFILE = {
    "full_name": "",
    "title": "",
    "location": "",
    "linkedin": "",
    "github": "",
    "portfolio": "",
    "skills": [],
    "target_roles": [],
    "sectors": [],
    "modality": "",
    "preferred_location": "",
    "min_salary": "",
    "experience_level": "",
}


def get_all_jobs(
    db: Session,
    limit: int = 50,
    status: str | None = None,
) -> list[Job]:
    limit = max(1, min(limit, 500))
    query = db.query(Job).order_by(Job.id.desc())
    if status:
        query = query.filter(Job.status == status)
    return query.limit(limit).all()


def get_job_by_id(db: Session, job_id: int) -> Job | None:
    return db.query(Job).filter(Job.id == job_id).first()


def get_job_by_url(db: Session, url: str) -> Job | None:
    return db.query(Job).filter(Job.url == url).first()


def get_job_by_external_id(
    db: Session, source: str, external_id: str
) -> Job | None:
    if not source or not external_id:
        return None
    return (
        db.query(Job)
        .filter(Job.source == source, Job.external_id == external_id)
        .first()
    )


def get_job_by_content_hash(db: Session, content_hash: str) -> Job | None:
    if not content_hash:
        return None
    return db.query(Job).filter(Job.content_hash == content_hash).first()


def _as_datetime(value) -> datetime | None:
    """Los scrapers devuelven datetime o None; la BD guarda DateTime."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
        except ValueError:
            return None
    return None


def save_jobs(
    db: Session,
    jobs: list[dict],
    search_query: str | None = None,
) -> list[Job]:
    now = datetime.utcnow()
    saved: list[Job] = []
    touched_fps: set[str] = set()

    for raw in jobs:
        data = normalize_job(raw)
        url = data["url"]
        title = data["title"]

        if not url or not title:
            continue

        fingerprint = fingerprint_of(
            title, data.get("company"), data.get("location")
        )
        published_at = _as_datetime(data.get("published_at"))
        content_hash = content_hash_of(data.get("description"))
        data["content_hash"] = content_hash

        # Dedup §15: external_id > URL > hash de contenido.
        existing = get_job_by_external_id(
            db, data["source"], data.get("external_id") or ""
        ) or get_job_by_url(db, url)
        if existing is None and content_hash:
            existing = get_job_by_content_hash(db, content_hash)

        if existing:
            # La oferta sigue publicada: refresca y marca el avistamiento.
            old_fp = existing.fingerprint
            for field in ("title", "company", "location", "description"):
                new_value = data.get(field) or ""
                if getattr(existing, field) != new_value and new_value:
                    setattr(existing, field, new_value)
            if search_query and existing.search_query != search_query:
                existing.search_query = search_query
            # La huella depende de titulo/empresa/ubicacion: si alguno
            # cambio (ej: re-encode), recalcular para no partir el grupo.
            new_fp = fingerprint_of(
                existing.title, existing.company, existing.location
            )
            if new_fp != old_fp:
                existing.fingerprint = new_fp
                if old_fp:
                    touched_fps.add(old_fp)
            if published_at and not existing.published_at:
                existing.published_at = published_at
                existing.published_text = data.get("published_text") or ""
            # Rellena campos normalizados que falten (sin pisar datos).
            for norm_field in ("external_id", "sector", "modality",
                               "salary", "content_hash"):
                if not getattr(existing, norm_field, None) and data.get(
                    norm_field
                ):
                    setattr(existing, norm_field, data[norm_field])
            for json_field in ("requirements", "responsibilities"):
                if not getattr(existing, json_field, None) and data.get(
                    json_field
                ):
                    setattr(
                        existing, json_field,
                        json.dumps(data[json_field], ensure_ascii=False),
                    )
            existing.last_seen_at = now
            db.add(existing)
            saved.append(existing)
            touched_fps.add(new_fp)
            continue

        job = Job(
            title=title,
            company=data.get("company") or "",
            location=data.get("location") or "",
            url=url,
            description=data.get("description") or "",
            source=data.get("source") or "computrabajo",
            search_query=search_query,
            published_text=data.get("published_text") or "",
            published_at=published_at,
            fingerprint=fingerprint,
            times_seen=1,
            last_seen_at=now,
            external_id=data.get("external_id"),
            requirements=json.dumps(data.get("requirements") or [],
                                    ensure_ascii=False),
            responsibilities=json.dumps(
                data.get("responsibilities") or [], ensure_ascii=False),
            sector=data.get("sector") or "",
            modality=data.get("modality") or "",
            salary=data.get("salary") or "",
            content_hash=content_hash,
        )
        db.add(job)
        saved.append(job)
        touched_fps.add(fingerprint)

    db.commit()

    # Republicaciones: todas las filas con la misma huella comparten
    # `times_seen` = N.o de publicaciones distintas del grupo.
    for fp in touched_fps:
        if not fp:
            continue
        count = (
            db.query(func.count(Job.id))
            .filter(Job.fingerprint == fp)
            .scalar()
            or 0
        )
        if count:
            db.query(Job).filter(Job.fingerprint == fp).update(
                {"times_seen": count, "last_seen_at": now},
                synchronize_session=False,
            )
    db.commit()

    for job in saved:
        db.refresh(job)

    return saved


def update_job_status(
    db: Session,
    job: Job,
    status: str,
    discard_reason: str | None = None,
    discard_note: str | None = None,
    application_status: str | None = None,
) -> Job:
    if status not in JOB_STATUSES:
        raise ValueError(
            f"Estado invalido: {status}. "
            f"Permitidos: {', '.join(JOB_STATUSES)}"
        )

    job.status = status

    if status == "discarded":
        job.discard_reason = discard_reason
        job.discard_note = discard_note
        job.decided_at = datetime.utcnow()
    elif status == "kept":
        job.discard_reason = None
        job.discard_note = None
        job.decided_at = datetime.utcnow()
    elif status == "applied":
        job.applied_at = job.applied_at or datetime.utcnow()
        job.decided_at = job.decided_at or datetime.utcnow()
        if application_status:
            job.application_status = application_status
    elif status == "opened":
        job.decided_at = job.decided_at or datetime.utcnow()
    elif status == "new":
        # Recuperar: vuelve a nueva sin borrar el historial de fechas.
        job.discard_reason = None
        job.discard_note = None

    if application_status and status != "applied":
        job.application_status = application_status

    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_stats(db: Session) -> dict:
    """Resumen honesto calculado solo con datos reales de la BD.
    Delega en el Analytics Agent (solo lectura)."""
    from app.agents.analytics_agent import summarize

    return summarize(db)


def get_profile(db: Session) -> dict:
    row = db.query(Profile).filter(Profile.id == 1).first()
    if not row:
        row = Profile(id=1, data=json.dumps(DEFAULT_PROFILE))
        db.add(row)
        db.commit()
        db.refresh(row)
    try:
        data = json.loads(row.data or "{}")
    except ValueError:
        data = {}
    merged = {**DEFAULT_PROFILE, **data}
    return merged


def save_profile(db: Session, data: dict) -> dict:
    row = db.query(Profile).filter(Profile.id == 1).first()
    if not row:
        row = Profile(id=1, data="{}")
        db.add(row)
    allowed = {key: data.get(key, DEFAULT_PROFILE[key]) for key in DEFAULT_PROFILE}
    row.data = json.dumps(allowed, ensure_ascii=False)
    db.add(row)
    db.commit()
    return get_profile(db)


def backfill_fingerprints(db: Session) -> int:
    """Recalcula huellas con los valores actuales y contadores de grupo.
    Idempotente. Devuelve cuantas filas actualizo."""
    rows = db.query(Job).all()
    touched = 0
    for job in rows:
        fresh = fingerprint_of(job.title, job.company, job.location)
        if job.fingerprint != fresh or not job.last_seen_at:
            job.fingerprint = fresh
            job.last_seen_at = job.last_seen_at or job.created_at
            db.add(job)
            touched += 1
    db.commit()

    # Recalcula contadores de todos los grupos.
    groups = [
        row[0]
        for row in db.query(Job.fingerprint, func.count(Job.id))
        .filter(Job.fingerprint.isnot(None))
        .group_by(Job.fingerprint)
        .all()
    ]
    for fingerprint in groups:
        count = (
            db.query(func.count(Job.id))
            .filter(Job.fingerprint == fingerprint)
            .scalar()
            or 0
        )
        db.query(Job).filter(Job.fingerprint == fingerprint).update(
            {"times_seen": count}, synchronize_session=False
        )
    db.commit()
    return touched


def save_analysis(
    db: Session,
    job: Job,
    match_score: float | None,
    matched: list[str] | None = None,
    missing: list[str] | None = None,
    detected_role: str | None = None,
    category: str | None = None,
    evidence: list[str] | None = None,
    experience: str | None = None,
) -> Job:
    """Persiste el resultado de analyze_job. Solo toca campos de
    analisis: nunca decisiones del usuario (status, descartes)."""
    job.match_score = match_score
    job.matched_skills = json.dumps(matched or [], ensure_ascii=False)
    job.missing_skills = json.dumps(missing or [], ensure_ascii=False)
    job.detected_role = detected_role
    job.category = category
    job.evidence = json.dumps(evidence or [], ensure_ascii=False)
    job.experience_required = experience
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def analyze_pending(db: Session, limit: int = 50) -> dict:
    """Analiza filas con descripcion pero sin score (backfill)."""
    from app.analysis.scorer import analyze_job

    limit = max(1, min(limit, 500))
    profile = get_profile(db)
    rows = (
        db.query(Job)
        .filter(Job.match_score.is_(None))
        .filter(Job.description.isnot(None))
        .filter(Job.description != "")
        .order_by(Job.id.desc())
        .limit(limit)
        .all()
    )
    analyzed = 0
    relevant = 0
    for row in rows:
        result = analyze_job(
            {"title": row.title or "",
             "description": row.description or ""},
            profile,
        )
        save_analysis(
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
    return {"analyzed": analyzed, "relevant": relevant}
