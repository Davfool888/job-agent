"""Capa de acceso a datos agnostica al motor.

`db` es un handle: Session (sqlite) o FirestoreDatabase (firestore).
Toda funcion publica devuelve Records (id siempre str) o dicts, nunca
ORM. El codigo de main/agents/discovery solo usa estas funciones mas
update_job_fields/refresh_job/persist_job: jamas SQL directo.
"""
from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.firestore_client import is_firestore
from app.database.firestore_client import is_firestore
from app.database.models import JOB_STATUSES
from app.database.models import Job
from app.database.models import Profile
from app.database.models import UserJobState
from app.database.models import UserProfile
from app.database.models import UserRichProfile
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

_LIST_FIELDS = (
    "matched_skills", "missing_skills", "evidence", "discovered_by",
    "requirements", "responsibilities", "search_profile_ids",
)


def _parse_list(value) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


class Record:
    """Registro en forma-app con acceso por atributo (vale para ambos
    motores; id siempre str)."""

    def __init__(self, id: str, data: dict):
        object.__setattr__(self, "id", str(id))
        object.__setattr__(self, "_data", dict(data))

    def __getattr__(self, name: str):
        return self._data.get(name)

    def __setattr__(self, name: str, value) -> None:
        if name in ("id", "_data"):
            object.__setattr__(self, name, value)
        else:
            self._data[name] = value

    def to_dict(self) -> dict:
        return {"id": self.id, **dict(self._data)}


def orm_to_record(row: Job) -> Record:
    data = {}
    for column in row.__table__.columns.keys():
        value = getattr(row, column)
        if column in _LIST_FIELDS:
            value = _parse_list(value)
        data[column] = value
    data["cv_generated"] = bool(data.get("cv_generated"))
    return Record(str(row.id), data)


def _to_orm_fields(data: dict) -> dict:
    """Convierte forma-app a columnas SQLite (listas -> JSON TEXT)."""
    fields = {}
    columns = set(Job.__table__.columns.keys()) - {"id"}
    for key, value in data.items():
        if key not in columns or key == "id":
            continue
        if key in _LIST_FIELDS and isinstance(value, list):
            value = json.dumps(value, ensure_ascii=False)
        fields[key] = value
    return fields


# ---------------------------------------------------------------------------
# Primitivas de escritura/lectura (despachan segun el motor)
# ---------------------------------------------------------------------------

def get_jobs_by_ids(db, ids: list) -> list[Record]:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_jobs_by_ids(db, [str(i) for i in ids])
    rows = db.query(Job).filter(
        Job.id.in_([int(i) for i in ids])
    ).all() if ids else []
    return [orm_to_record(row) for row in rows]


def iter_all_jobs(db, limit: int = 5000) -> list[Record]:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.iter_all_jobs(db, limit=limit)
    rows = db.query(Job).order_by(Job.id.desc()).limit(limit).all()
    return [orm_to_record(row) for row in rows]


def create_job_row(db, data: dict) -> Record:
    """Crea una oferta desde dict en forma-app. Devuelve Record."""
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.create_job_row(db, data)
    row = Job(**_to_orm_fields(data))
    db.add(row)
    db.commit()
    db.refresh(row)
    return orm_to_record(row)


def update_job_fields(db, job_or_id, fields: dict) -> Record:
    """Actualiza campos (forma-app) y devuelve el Record fresco."""
    fields = {k: v for k, v in fields.items() if k != "id"}
    if is_firestore(db):
        from app.database import firestore_repo as fs

        job_id = job_or_id.id if isinstance(job_or_id, Record) else job_or_id
        return fs.update_job_fields(db, job_id, fields)
    job_id = job_or_id.id if isinstance(job_or_id, Record) else job_or_id
    row = db.query(Job).filter(Job.id == int(job_id)).first()
    if row is None:
        raise ValueError(f"Oferta {job_id} no encontrada.")
    for key, value in _to_orm_fields(fields).items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return orm_to_record(row)


def persist_job(db, job: Record) -> Record:
    """Escribe el Record completo (reemplaza db.add+commit manual)."""
    data = job.to_dict()
    data.pop("id", None)
    return update_job_fields(db, job.id, data)


def refresh_job(db, job: Record) -> Record:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        fresh = fs.get_job(db, job.id)
    else:
        row = db.query(Job).filter(Job.id == int(job.id)).first()
        fresh = orm_to_record(row) if row else None
    if fresh is None:
        raise ValueError(f"Oferta {job.id} no encontrada.")
    return fresh


def delete_job(db, job_id) -> bool:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.delete_job(db, job_id)
    row = db.query(Job).filter(Job.id == int(job_id)).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def count_by_fingerprint(db, fingerprint: str) -> int:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.count_by_fingerprint(db, fingerprint)
    if not fingerprint:
        return 0
    return (
        db.query(func.count(Job.id))
        .filter(Job.fingerprint == fingerprint)
        .scalar()
        or 0
    )


def update_fingerprint_group(db, fingerprint: str, fields: dict) -> int:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.update_fingerprint_group(db, fingerprint, fields)
    if not fingerprint:
        return 0
    orm_fields = _to_orm_fields(fields)
    updated = (
        db.query(Job)
        .filter(Job.fingerprint == fingerprint)
        .update(orm_fields, synchronize_session=False)
    )
    db.commit()
    return updated


def tag_discovered(db, ids: list, slug: str) -> None:
    """Agrega el slug de la query a `discovered_by` sin duplicar."""
    if not ids or not slug:
        return
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.tag_discovered(db, ids, slug)
    rows = db.query(Job).filter(
        Job.id.in_([int(i) for i in ids])
    ).all() if ids else []
    for row in rows:
        try:
            current = json.loads(row.discovered_by or "[]")
        except ValueError:
            current = []
        if slug not in current:
            current.append(slug)
            row.discovered_by = json.dumps(current, ensure_ascii=False)
            db.add(row)
    db.commit()


def get_unscored_jobs(db, limit: int = 50) -> list[Record]:
    limit = max(1, min(limit, 500))
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_unscored_jobs(db, limit=limit)
    rows = (
        db.query(Job)
        .filter(Job.match_score.is_(None))
        .filter(Job.description.isnot(None))
        .filter(Job.description != "")
        .order_by(Job.id.desc())
        .limit(limit)
        .all()
    )
    return [orm_to_record(row) for row in rows]


def log_interaction(db, type: str, job_id=None, application_id=None,
                    metadata: dict | None = None):
    """Registra interaccion (append-only). Solo Firestore: SQLite no
    tiene esta tabla y su comportamiento no cambia."""
    if not is_firestore(db):
        return None
    from app.database import firestore_repo as fs

    return fs.log_interaction(db, type, job_id, application_id, metadata)


def is_firestore_handle(db) -> bool:
    from app.database.firestore_client import is_firestore

    return is_firestore(db)


def register_job_view(db, job: Record) -> Record:
    """Suma una vista (view_count + timestamps). Solo Firestore: SQLite
    no tiene estas columnas y su comportamiento no cambia."""
    if not is_firestore(db):
        return job
    now = datetime.utcnow()
    return update_job_fields(db, job.id, {
        "viewed": True,
        "view_count": (job.view_count or 0) + 1,
        "first_viewed_at": job.first_viewed_at or now,
        "last_viewed_at": now,
    })


def register_cv_version(db, job_id, meta: dict) -> dict | None:
    """Registra metadatos del CV en cvs/ (solo Firestore; en SQLite la
    info vive en columnas cv_generated/cv_path y archivos locales)."""
    if not is_firestore(db):
        return None
    from app.database import firestore_repo as fs

    return fs.register_cv_version(db, job_id, meta)


def get_customized_cv(db, job_id) -> dict | None:
    """Ensambla el CV personalizado de una oferta sin consumir IA.

    Devuelve None si nunca se genero. Estructura conceptual:
    job -> customized_cv {analysis, selected_experience,
    selected_skills, generated_content, latex, pdf, created_at, version}.
    """
    import json as _json

    from app.cv import generator as cvgen

    job = get_job_by_id(db, job_id)
    if not job:
        return None
    directory = cvgen.job_cv_dir(job.id)
    tex_path = directory / "cv.tex"
    if not job.cv_generated or not tex_path.exists():
        # Generado segun flags pero archivos ausentes = ERROR honesto.
        if job.cv_generated:
            return {
                "state": "ERROR",
                "job_id": job.id,
                "error": "El CV estaba marcado como generado pero los "
                "archivos no existen (cv.tex ausente). Regeneralo.",
            }
        return None
    pdf_path = directory / "cv.pdf"
    content_path = directory / "cv_content.json"
    analysis_path = directory / "analysis.json"
    generated_content = None
    if content_path.exists():
        try:
            generated_content = _json.loads(
                content_path.read_text(encoding="utf-8"))
        except ValueError:
            generated_content = None
    analysis = None
    if analysis_path.exists():
        try:
            analysis = _json.loads(
                analysis_path.read_text(encoding="utf-8"))
        except ValueError:
            analysis = None
    version = 1
    if is_firestore(db):
        from app.database import firestore_repo as fs

        versions = fs.list_cvs_for_job(db, job.id)
        if versions:
            version = versions[0].get("version", 1)
    created_at = None
    try:
        from datetime import datetime as _dt

        created_at = _dt.fromtimestamp(
            tex_path.stat().st_mtime).isoformat()
    except OSError:
        created_at = None
    selected_experience = []
    selected_skills = []
    if isinstance(generated_content, dict):
        selected_experience = generated_content.get(
            "selected_experience", []) or []
        selected_skills = generated_content.get("skills", []) or []
    return {
        "state": "READY",
        "job_id": job.id,
        "version": version,
        "analysis": analysis,
        "selected_experience": selected_experience,
        "selected_skills": selected_skills,
        "generated_content": generated_content,
        "latex_available": True,
        "pdf_available": pdf_path.exists(),
        "created_at": created_at,
        "download_tex": f"/jobs/{job.id}/cv/download?format=tex",
        "download_pdf": (
            f"/jobs/{job.id}/cv/download?format=pdf"
            if pdf_path.exists() else None
        ),
    }


# ---------------------------------------------------------------------------
# Lecturas publicas
# ---------------------------------------------------------------------------

def get_all_jobs(
    db: Session,
    limit: int = 50,
    status: str | None = None,
    since: datetime | None = None,
    uid: str | None = None,
    email: str | None = None,
) -> list[Record]:
    """Ofertas visibles para la sesion, con estado efectivo del usuario.

    Sin uid: comportamiento historico (todo global). Con uid: solo
    ofertas del usuario (owner_uid) o encontradas por sus perfiles,
    con su estado propio superpuesto (el global queda como legado).
    """
    if not uid:
        if is_firestore(db):
            from app.database import firestore_repo as fs

            return fs.list_jobs(db, limit=limit, status=status, since=since)
        limit = max(1, min(limit, 500))
        query = db.query(Job).order_by(Job.id.desc())
        if status:
            query = query.filter(Job.status == status)
        if since:
            query = query.filter(
                (Job.found_at.isnot(None) & (Job.found_at >= since))
                | ((Job.found_at.is_(None)) & (Job.created_at >= since))
            )
        return [orm_to_record(row) for row in query.limit(limit).all()]

    # Con uid: filtrar por owner_uid o por perfiles de búsqueda del usuario
    from app.services.search_profiles import _is_guest, GUEST_OWNER
    store_uid = GUEST_OWNER if _is_guest(uid, email) else uid

    if is_firestore(db):
        from app.database import firestore_repo as fs

        candidates = fs.list_jobs(db, limit=5000, status=None, since=since)
    else:
        query = db.query(Job).order_by(Job.id.desc())
        if since:
            query = query.filter(
                (Job.found_at.isnot(None) & (Job.found_at >= since))
                | ((Job.found_at.is_(None)) & (Job.created_at >= since))
            )
        candidates = [orm_to_record(row) for row in query.limit(5000).all()]

    # Filtrar por owner_uid o por perfiles de búsqueda
    visible = []
    for record in candidates:
        # Verificar si la oferta pertenece al usuario
        if getattr(record, 'owner_uid', None) == store_uid:
            visible.append(record)
            continue
        # Verificar si fue encontrada por un perfil del usuario
        profile_ids = _parse_list(getattr(record, 'search_profile_ids', None))
        if profile_ids:
            from app.services import search_profiles as profiles
            for pid in profile_ids:
                profile = profiles.get_profile(db, pid)
                if profile and profile.get('owner_uid') == store_uid:
                    visible.append(record)
                    break

    # Aplicar estado del usuario
    states = _all_user_states(db, store_uid)
    out: list[Record] = []
    for record in visible:
        record = _apply_state(record, states.get(record.id))
        if status and record.status != status:
            continue
        out.append(record)
    limit = max(1, min(limit, 500))
    return out[:limit]


def get_job_by_id(
    db: Session, job_id, uid: str | None = None, email: str | None = None
) -> Record | None:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        record = fs.get_job(db, job_id)
    else:
        try:
            numeric = int(job_id)
        except (TypeError, ValueError):
            return None
        row = db.query(Job).filter(Job.id == numeric).first()
        record = orm_to_record(row) if row else None
    if record is None or not uid:
        return record
    if record.id not in _visible_ids(db, uid, email):
        return None
    return _apply_state(
        record,
        get_user_job_state(db, _store_uid(uid, email), record.id))


def get_job_by_url(db: Session, url: str) -> Record | None:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_by_url(db, url)
    row = db.query(Job).filter(Job.url == url).first()
    return orm_to_record(row) if row else None


def get_job_by_external_id(
    db: Session, source: str, external_id: str
) -> Record | None:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_by_external(db, source, external_id)
    if not source or not external_id:
        return None
    row = (
        db.query(Job)
        .filter(Job.source == source, Job.external_id == external_id)
        .first()
    )
    return orm_to_record(row) if row else None


def get_job_by_content_hash(db: Session, content_hash: str) -> Record | None:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_by_hash(db, content_hash)
    if not content_hash:
        return None
    row = db.query(Job).filter(Job.content_hash == content_hash).first()
    return orm_to_record(row) if row else None


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
    search_profile_id: str | None = None,
    uid: str | None = None,
    email: str | None = None,
) -> list[Record]:
    now = datetime.utcnow()
    saved: list[Record] = []
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

        # Dedup §15: external_id > URL > hash de contenido.
        existing = get_job_by_external_id(
            db, data["source"], data.get("external_id") or ""
        ) or get_job_by_url(db, url)
        if existing is None and content_hash:
            existing = get_job_by_content_hash(db, content_hash)

        if existing:
            # La oferta sigue publicada: refresca y marca el avistamiento.
            old_fp = existing.fingerprint
            updates: dict = {}
            for field in ("title", "company", "location", "description"):
                new_value = data.get(field) or ""
                if getattr(existing, field, None) != new_value and new_value:
                    updates[field] = new_value
            if search_query and existing.search_query != search_query:
                updates["search_query"] = search_query
            # La huella depende de titulo/empresa/ubicacion: si alguno
            # cambio (ej: re-encode), recalcular para no partir el grupo.
            merged_title = updates.get("title", existing.title)
            merged_company = updates.get("company", existing.company)
            merged_location = updates.get("location", existing.location)
            new_fp = fingerprint_of(
                merged_title, merged_company, merged_location
            )
            if new_fp != old_fp:
                updates["fingerprint"] = new_fp
                if old_fp:
                    touched_fps.add(old_fp)
            if published_at and not existing.published_at:
                updates["published_at"] = published_at
                updates["published_text"] = data.get("published_text") or ""
            # Rellena campos normalizados que falten (sin pisar datos).
            for norm_field in ("external_id", "sector", "modality",
                               "salary", "content_hash"):
                if not getattr(existing, norm_field, None) and data.get(
                    norm_field
                ):
                    updates[norm_field] = data[norm_field]
            if content_hash and not getattr(existing, "content_hash", None):
                updates["content_hash"] = content_hash
            for json_field in ("requirements", "responsibilities"):
                if not getattr(existing, json_field, None) and data.get(
                    json_field
                ):
                    updates[json_field] = data[json_field]
            # El perfil tambien encontro esta oferta: unir sin duplicar.
            if search_profile_id:
                merged_profiles = _merge_profile_ids(
                    getattr(existing, "search_profile_ids", None),
                    search_profile_id,
                )
                if merged_profiles != (
                    getattr(existing, "search_profile_ids", None) or []
                ):
                    updates["search_profile_ids"] = merged_profiles
            updates["last_seen_at"] = now
            existing = update_job_fields(db, existing.id, updates)
            saved.append(existing)
            touched_fps.add(new_fp)
            continue

        job_data = {
            "title": title,
            "company": data.get("company") or "",
            "location": data.get("location") or "",
            "url": url,
            "description": data.get("description") or "",
            "source": data.get("source") or "computrabajo",
            "search_query": search_query,
            "published_text": data.get("published_text") or "",
            "published_at": published_at,
            "fingerprint": fingerprint,
            "times_seen": 1,
            "last_seen_at": now,
            "found_at": now,
            "first_seen_at": now,
            "search_profile_ids": (
                [search_profile_id] if search_profile_id else []
            ),
            "external_id": data.get("external_id"),
            "requirements": data.get("requirements") or [],
            "responsibilities": data.get("responsibilities") or [],
            "sector": data.get("sector") or "",
            "modality": data.get("modality") or "",
            "salary": data.get("salary") or "",
            "content_hash": content_hash,
        }
        # Asociar oferta con usuario (si hay sesión)
        if uid:
            from app.services.search_profiles import _is_guest, GUEST_OWNER
            store_uid = GUEST_OWNER if _is_guest(uid, email) else uid
            job_data["owner_uid"] = store_uid
        job = create_job_row(db, job_data)
        saved.append(job)
        touched_fps.add(fingerprint)

    # Republicaciones: todas las filas con la misma huella comparten
    # `times_seen` = N.o de publicaciones distintas del grupo.
    for fp in touched_fps:
        if not fp:
            continue
        count = count_by_fingerprint(db, fp)
        if count:
            update_fingerprint_group(
                db, fp, {"times_seen": count, "last_seen_at": now}
            )

    return [refresh_job(db, job) for job in saved]


def _merge_profile_ids(current, profile_id: str | None) -> list:
    """Une un id de perfil a la lista sin duplicar."""
    merged = _parse_list(current)
    if profile_id and profile_id not in merged:
        merged.append(profile_id)
    return merged


def update_job_status(
    db: Session,
    job: Record,
    status: str,
    discard_reason: str | None = None,
    discard_note: str | None = None,
    application_status: str | None = None,
) -> Record:
    if status not in JOB_STATUSES:
        raise ValueError(
            f"Estado invalido: {status}. "
            f"Permitidos: {', '.join(JOB_STATUSES)}"
        )

    previous = job.status
    fields: dict = {"status": status}

    if status == "discarded":
        fields["discard_reason"] = discard_reason
        fields["discard_note"] = discard_note
        fields["decided_at"] = datetime.utcnow()
    elif status == "kept":
        fields["discard_reason"] = None
        fields["discard_note"] = None
        fields["decided_at"] = datetime.utcnow()
    elif status == "applied":
        fields["applied_at"] = job.applied_at or datetime.utcnow()
        fields["decided_at"] = job.decided_at or datetime.utcnow()
        if application_status:
            fields["application_status"] = application_status
    elif status == "opened":
        fields["decided_at"] = job.decided_at or datetime.utcnow()
    elif status == "new":
        # Recuperar: vuelve a nueva sin borrar el historial de fechas.
        fields["discard_reason"] = None
        fields["discard_note"] = None

    if application_status and status != "applied":
        fields["application_status"] = application_status

    updated = update_job_fields(db, job.id, fields)

    if is_firestore(db):
        from app.database import firestore_repo as fs

        if status == "discarded":
            log_interaction(db, "JOB_DISCARDED", job.id, None, {
                "from": previous, "to": status,
                "reason": discard_reason,
            })
        elif status == "kept":
            log_interaction(db, "JOB_SAVED", job.id)
        elif status == "new" and previous == "discarded":
            log_interaction(db, "JOB_REOPENED", job.id)
        elif status == "applied":
            application = fs.find_application_by_job(db, updated.id)
            if application is None:
                application = fs.create_application(db, {
                    "job_id": updated.id,
                    "company": updated.company or "",
                    "role": updated.detected_role or updated.title or "",
                    "status": "APPLIED",
                    "applied_at": updated.applied_at,
                    "application_url": updated.url or "",
                    "notes": "",
                })
                fs.append_application_event(db, application["id"], {
                    "type": "APPLICATION_CREATED",
                    "from": None,
                    "to": "APPLIED",
                    "notes": "",
                })
            if application_status:
                fs.update_application(db, application["id"], {
                    "status": fs.APP_STAGE_TO_FS.get(
                        (application_status or "").strip().lower(), "APPLIED"),
                })
                fs.append_application_event(db, application["id"], {
                    "type": "STATUS_CHANGED",
                    "from": application.get("status"),
                    "to": fs.APP_STAGE_TO_FS.get(
                        (application_status or "").strip().lower(), "APPLIED"),
                    "notes": f"stage: {application_status}",
                })

    return updated


def get_stats(db: Session, uid: str | None = None, email: str | None = None) -> dict:
    """Resumen honesto calculado solo con datos reales de la BD.
    Delega en el Analytics Agent (solo lectura)."""
    from app.agents.analytics_agent import summarize

    return summarize(db, uid=uid, email=email)


def get_profile(db: Session, uid: str | None = None, email: str | None = None) -> dict:
    """Perfil visible para la sesión.
    
    - Admin/sin sesión: perfil base global
    - Invitado: datos demo de Andrés Felipe
    - Usuario Google: solo su perfil (vacío si no ha guardado)
    """
    # Sin sesión o admin: perfil base global
    if not uid or _is_admin(email):
        if is_firestore(db):
            from app.database import firestore_repo as fs

            merged = fs.get_profile_doc(db)
            _merge_rich_profile(merged)
            return merged
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
        _merge_rich_profile(merged)
        return merged

    # Invitado: datos demo de Andrés Felipe
    from app.services.search_profiles import _is_guest, GUEST_OWNER
    if _is_guest(uid, email):
        _ensure_guest_demo_flat(db)
        stored = _stored_user_flat(db, GUEST_OWNER)
        out = {key: stored.get(key, DEFAULT_PROFILE[key])
               for key in DEFAULT_PROFILE}
        out["scope"] = "demo"
        return out

    # Usuario Google: solo su perfil (vacío si no ha guardado)
    stored = _stored_user_flat(db, uid)
    out = {key: stored.get(key, DEFAULT_PROFILE[key])
           for key in DEFAULT_PROFILE}
    out["scope"] = "own"
    return out


def _merge_rich_profile(merged: dict) -> None:
    """Une base_cv.json (fuente rica modular) al perfil plano, de forma
    aditiva: union de skills/target_roles + passthrough de secciones
    (experience, education, projects, certifications) con perspectivas.
    Consumidores viejos siguen funcionando."""
    try:
        from app.agents.cv_agent import CVAgent

        rich = CVAgent().base_profile() or {}
    except Exception:
        return
    if not isinstance(rich, dict):
        return
    try:
        from app.profile.perspectives import flatten_profile_skills
    except Exception:
        return
    flat = [s for s in (merged.get("skills") or []) if str(s).strip()]
    for skill in flatten_profile_skills(rich):
        if skill not in flat:
            flat.append(skill)
    merged["skills"] = flat[:60]
    targets = [t for t in (merged.get("target_roles") or []) if str(t).strip()]
    for target in rich.get("target_roles") or []:
        if target and target not in targets:
            targets.append(target)
    merged["target_roles"] = targets[:20]
    for section in ("experience", "education", "projects", "certifications",
                    "personal", "professional_summary", "languages"):
        if section not in merged and section in rich:
            merged[section] = rich[section]
    merged["_rich_source"] = "base_cv.json"


def get_rich_profile(db: Session) -> dict:
    """Perfil modular completo para administracion (base bloqueada +
    secciones con perspectivas)."""
    from app.agents.cv_agent import CVAgent
    from app.profile.perspectives import SECTIONS
    from app.profile.perspectives import validate_profile

    agent = CVAgent()
    rich = agent.base_profile() or {}
    flat = get_profile(db)
    from app.profile import schema as profile_schema

    normalized, schema_warnings = profile_schema.normalize_rich_profile(rich)
    rich = normalized
    for section in SECTIONS:
        if not isinstance(rich.get(section), list):
            rich[section] = []
    rich["_flat"] = {k: flat.get(k) for k in (
        "full_name", "title", "location", "linkedin", "github", "portfolio",
        "skills", "target_roles", "sectors", "modality",
        "preferred_location", "min_salary", "experience_level",
    )}
    rich["_warnings"] = validate_profile(rich) + schema_warnings
    return rich


def save_rich_profile(data: dict) -> dict:
    """Persiste base_cv.json (fuente de verdad modular). Valida y
    devuelve advertencias sin borrar nada."""
    import json as _json

    from app.agents.cv_agent import CVAgent
    from app.config import BASE_CV_PATH
    from app.profile import schema as profile_schema
    from app.profile.perspectives import SECTIONS
    from app.profile.perspectives import validate_profile

    if not isinstance(data, dict):
        raise ValueError("Perfil invalido: se esperaba un objeto")

    current = CVAgent().base_profile() or {}
    merged = dict(current)
    for key in ("personal", "professional_summary", "skills", "languages",
                "certifications", "target_roles", "technical_skills",
                "soft_skills", "years_experience"):
        if key in data:
            merged[key] = data[key]
    for section in SECTIONS:
        if section in data and isinstance(data[section], list):
            merged[section] = data[section]
    normalized, schema_warnings = profile_schema.normalize_rich_profile(
        merged)
    BASE_CV_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASE_CV_PATH.write_text(
        _json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    warnings = validate_profile(normalized) + schema_warnings
    return {"profile": normalized, "warnings": warnings}


def save_profile(db: Session, data: dict) -> dict:
    from app.profile import schema as profile_schema

    # Normaliza variantes contra catalogos (modalidad, nivel,
    # cargos, sectores, ciudades, salario) sin borrar texto libre.
    normalized, _ = profile_schema.normalize_flat_profile(data or {})
    if is_firestore(db):
        from app.database import firestore_repo as fs

        merged = fs.save_profile_doc(db, normalized, DEFAULT_PROFILE)
        _merge_rich_profile(merged)
        return merged
    row = db.query(Profile).filter(Profile.id == 1).first()
    if not row:
        row = Profile(id=1, data="{}")
        db.add(row)
    allowed = {key: normalized.get(key, DEFAULT_PROFILE[key]) for key in DEFAULT_PROFILE}
    row.data = json.dumps(allowed, ensure_ascii=False)
    db.add(row)
    db.commit()
    return get_profile(db)


# ---------------------------------------------------------------------------
# Perfiles por usuario (§login). Solo el ADMIN_EMAIL ve y edita el perfil
# base global; cualquier otro usuario con sesion usa su propio perfil,
# que empieza en blanco y solo existe cuando guarda datos.
# Sin sesion (modo local sin Firebase) se conserva el global historico.
# ---------------------------------------------------------------------------

def _is_admin(email: str | None) -> bool:
    from app.config import is_admin_email

    return is_admin_email(email)


def _stored_user_flat(db, uid: str) -> dict:
    """Datos planos guardados por el usuario ({} si nunca guardo)."""
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_user_profile(db, uid)
    row = db.query(UserProfile).filter(UserProfile.uid == uid).first()
    if not row:
        return {}
    try:
        data = json.loads(row.data or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def _stored_user_rich(db, uid: str) -> dict:
    """Perfil estructurado guardado por el usuario ({} si nunca guardo)."""
    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_user_rich_profile(db, uid)
    row = db.query(UserRichProfile).filter(
        UserRichProfile.uid == uid).first()
    if not row:
        return {}
    try:
        data = json.loads(row.data or "{}")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def get_profile_for(
    db: Session, uid: str | None, email: str | None
) -> dict:
    """Perfil plano segun quien llama. Admin/sin sesion -> base global;
    invitado -> demo compartida (siempre con datos de prueba);
    otro usuario -> solo lo suyo (en blanco si nunca guardo)."""
    if not uid or _is_admin(email):
        out = get_profile(db)
        out["scope"] = "admin" if uid else "shared"
        return out
    from app.services.search_profiles import GUEST_OWNER
    from app.services.search_profiles import _is_guest

    if _is_guest(uid, email):
        _ensure_guest_demo_flat(db)
        stored = _stored_user_flat(db, GUEST_OWNER)
        out = {key: stored.get(key, DEFAULT_PROFILE[key])
               for key in DEFAULT_PROFILE}
        out["scope"] = "demo"
        return out
    stored = _stored_user_flat(db, uid)
    # Solo claves conocidas; jamas se mezcla el perfil base global.
    out = {key: stored.get(key, DEFAULT_PROFILE[key])
           for key in DEFAULT_PROFILE}
    out["scope"] = "own"
    return out


def save_profile_for(
    db: Session, uid: str | None, email: str | None, data: dict
) -> dict:
    """Guarda el perfil plano. No-admin escribe SOLO su registro."""
    if not uid or _is_admin(email):
        out = save_profile(db, data or {})
        out["scope"] = "admin" if uid else "shared"
        return out
    from app.services.search_profiles import GUEST_OWNER
    from app.services.search_profiles import _is_guest

    store_uid = GUEST_OWNER if _is_guest(uid, email) else uid
    from app.profile import schema as profile_schema

    normalized, _ = profile_schema.normalize_flat_profile(data or {})
    allowed = {key: normalized.get(key, DEFAULT_PROFILE[key])
               for key in DEFAULT_PROFILE}
    if is_firestore(db):
        from app.database import firestore_repo as fs

        fs.save_user_profile(db, store_uid, allowed)
    else:
        row = db.query(UserProfile).filter(
            UserProfile.uid == store_uid).first()
        if not row:
            row = UserProfile(uid=store_uid, data="{}")
            db.add(row)
        row.data = json.dumps(allowed, ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
    return get_profile_for(db, uid, email)


GUEST_DEMO_FLAT: dict = {
    "full_name": "Andrés Felipe Ramírez",
    "title": "Ingeniero de Software",
    "location": "Bogotá, Colombia",
    "linkedin": "",
    "github": "",
    "portfolio": "",
    "skills": ["Python", "SQL", "Power BI", "Excel", "Pandas", "NumPy",
               "FastAPI", "JavaScript", "React", "Git", "PostgreSQL",
               "REST APIs"],
    "target_roles": ["Data Analyst", "Data Engineer Junior",
                     "Python Developer Junior"],
    "sectors": ["Tecnología", "Servicios Financieros", "Retail",
                "Consultoría"],
    "modality": "Híbrido",
    "preferred_location": "Bogotá, Colombia",
    "min_salary": "3500000",
    "experience_level": "Junior",
}

GUEST_DEMO_RICH: dict = {
    "personal": {
        "first_name": "Andrés Felipe",
        "last_name": "Ramírez Torres",
        "title": "Ingeniero de Software",
        "location": "Bogotá, Colombia",
        "email": "andres.ramirez.dev@example.com",
        "secondary_email": "andres.ramirez.work@example.com",
        "phone": "+57 310 555 4821",
        "secondary_phone": "+57 315 555 7394",
        "linkedin": "https://linkedin.com/in/andres-ramirez-dev",
        "github": "https://github.com/andresramirez-dev",
        "portfolio": "https://andresramirez.dev",
        "address": "Calle 98 # 18-42, Bogotá",
        "preferred_city_id": "bogota",
        "preferred_location": "Bogotá, Colombia",
        "preferred_modality": "HYBRID",
    },
    "professional_summary": (
        "Ingeniero de Software con experiencia en análisis de datos, "
        "automatización de procesos y desarrollo de soluciones utilizando "
        "Python, SQL, Power BI y herramientas de procesamiento de "
        "información. Interesado en posiciones junior relacionadas con "
        "análisis de datos, Business Intelligence, ingeniería de datos y "
        "desarrollo backend con Python."),
    "years_experience": 1,
    "technical_skills": ["Python", "SQL", "Power BI", "Excel", "Pandas",
                         "NumPy", "FastAPI", "JavaScript", "React", "Git",
                         "PostgreSQL", "REST APIs"],
    "soft_skills": ["Pensamiento analítico", "Comunicación y trabajo en equipo",
                    "Orientación a resultados", "Atención al detalle",
                    "Pensamiento crítico", "Adaptabilidad", "Organización",
                    "Resolución de problemas", "Aprendizaje autónomo", "Trabajo en equipo"],
    "target_roles": ["Data Analyst", "BI Analyst", "Data Engineer Junior",
                     "Python Developer Junior", "Backend Developer Junior",
                     "Financial Data Analyst"],
    # skills para el template (claves: analysis, languages, bi, databases, automation, backend, ml, tools)
    "skills": {
        "analysis": ["EDA (análisis exploratorio de datos)", "limpieza", "transformación", "segmentación",
                     "filtrado", "consolidación", "cruces de información", "KPIs", "indicadores",
                     "reportes", "análisis comercial"],
        "languages": ["Python", "SQL", "JavaScript", "Pandas", "NumPy"],
        "bi": ["Power BI", "Power Query", "DAX", "Excel avanzado", "tablas dinámicas",
               "dashboards", "KPIs", "indicadores", "reportes", "visualización de datos"],
        "databases": ["SQL", "MySQL", "MariaDB", "PostgreSQL", "SQLite", "MongoDB"],
        "automation": ["Python", "Google Apps Script", "APIs REST", "consumo de APIs",
                       "automatización de procesos", "procesamiento de información"],
        "backend": ["FastAPI", "Flask"],
        "ml": ["Scikit-learn", "YOLOv8", "OpenCV", "Roboflow", "procesamiento de imágenes"],
        "tools": ["Git", "GitHub", "Docker", "Linux", "WSL", "Google Colab", "Visual Studio Code"],
    },
    # skills_groups para compatibilidad con template (mismo contenido que skills)
    "skills_groups": {
        "analysis": ["EDA (análisis exploratorio de datos)", "limpieza", "transformación", "segmentación",
                     "filtrado", "consolidación", "cruces de información", "KPIs", "indicadores",
                     "reportes", "análisis comercial"],
        "languages": ["Python", "SQL", "JavaScript", "Pandas", "NumPy"],
        "bi": ["Power BI", "Power Query", "DAX", "Excel avanzado", "tablas dinámicas",
               "dashboards", "KPIs", "indicadores", "reportes", "visualización de datos"],
        "databases": ["SQL", "MySQL", "MariaDB", "PostgreSQL", "SQLite", "MongoDB"],
        "automation": ["Python", "Google Apps Script", "APIs REST", "consumo de APIs",
                       "automatización de procesos", "procesamiento de información"],
        "backend": ["FastAPI", "Flask"],
        "ml": ["Scikit-learn", "YOLOv8", "OpenCV", "Roboflow", "procesamiento de imágenes"],
        "tools": ["Git", "GitHub", "Docker", "Linux", "WSL", "Google Colab", "Visual Studio Code"],
    },
    "other_knowledge": ["Lógica de programación", "programación orientada a objetos",
                        "estructuras de datos", "algoritmos", "APIs REST",
                        "arquitectura cliente-servidor", "fundamentos de desarrollo de software"],
    "other_studies": [
        {"title": "Curso de DAX para Power BI", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso de Excel Analytics con AI y Python", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso de Power BI", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso de Python Intermedio: Comprehensions, Lambdas y Manejo de Errores", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso Básico de Algoritmos y Pensamiento Lógico", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso de Introducción al Desarrollo Backend", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso de Docker: Fundamentos", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso Práctico de JavaScript", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Fundamentos de Ingeniería de Software", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Curso de Introducción a la Terminal y Línea de Comandos", "institution": "Platzi", "start_date": "2021", "end_date": "2026"},
        {"title": "Inglés — Nivel B1 en formación", "institution": "Smart Language Academy", "start_date": "2025", "end_date": "Actualidad"},
    ],
    "languages": [
        {"id": "lang1", "language": "en",
         "academy": "Global Language Institute",
         "level": "B2", "listening": "B2", "reading": "B2",
         "writing": "B1", "speaking": "B1"},
        {"id": "lang2", "language": "pt",
         "academy": "Centro de Idiomas Modernos",
         "level": "A2", "listening": "A2", "reading": "A2",
         "writing": "A1", "speaking": "A2"},
    ],
    "experiences": [
        {
            "company": "Banco de Bogotá",
            "title": "Ejecutivo de Nómina para Empresas Cooperativas — Análisis de Información Empresarial y Comercial",
            "city": "Bogotá, Colombia",
            "modality": "Híbrido",
            "start_date": "Mar 2025",
            "end_date": "Dic 2025",
            "is_current": False,
            "description": "Analizar información empresarial y financiera de más de 10.000 registros para apoyar la toma de decisiones comerciales, utilizando herramientas de análisis de datos y automatización.",
            "bullets": [
                "Analicé y consolidé bases de datos con más de 10.000 registros utilizando Excel avanzado y Python para limpieza, validación, eliminación de duplicados, filtrado y segmentación de información.",
                "Realicé cruces de información entre fuentes internas y externas (incluyendo fuentes institucionales) para analizar variables empresariales como tamaño de empresa, número de empleados, presupuesto y nivel de endeudamiento, generando indicadores para apoyar decisiones comerciales.",
                "Desarrollé soluciones de automatización con Python y Google Apps Script para agilizar tareas de procesamiento, organización y consolidación de información.",
                "Consulté y realicé seguimiento a un volumen diario de empresas (más de 100 consultadas, cerca de 30 contactadas y entre 30-40 en seguimiento activo), aplicando criterios de análisis de datos para priorizar oportunidades.",
                "Gestioné información relacionada con productos financieros (créditos, CDT, tarjetas de crédito, depósitos y fiducias) de acuerdo con el perfil de cada empresa/cliente, identificado mediante análisis de datos.",
            ],
            "technical_skills": ["Python", "SQL", "Power BI", "Excel", "Pandas", "DAX", "Google Apps Script"],
            "soft_skills": ["Análisis", "Comunicación", "Organización", "Trabajo en equipo"],
        },
        {
            "company": "Banco de Bogotá",
            "title": "Asesor Comercial (Prácticas)",
            "city": "Bogotá, Colombia",
            "modality": "Presencial",
            "start_date": "Oct 2023",
            "end_date": "Oct 2024",
            "is_current": False,
            "description": "Apoyar procesos comerciales y operativos relacionados con clientes, productos financieros y gestión de información.",
            "bullets": [
                "Gestioné y validé información de clientes y productos financieros mediante Excel y plataformas internas, realizando consulta y seguimiento de datos.",
                "Atendí y gestioné clientes, adquiriendo experiencia en productos financieros, operaciones bancarias y procesos comerciales.",
                "Verifiqué información y documentación de clientes, garantizando el cumplimiento de los procedimientos establecidos por la entidad.",
            ],
            "technical_skills": ["Excel", "Plataformas bancarias", "Análisis financiero"],
            "soft_skills": ["Atención al cliente", "Comunicación", "Trabajo en equipo"],
        },
    ],
    "experience": [
        {
            "company": "Banco de Bogotá",
            "title": "Ejecutivo de Nómina para Empresas Cooperativas — Análisis de Información Empresarial y Comercial",
            "city": "Bogotá, Colombia",
            "modality": "Híbrido",
            "start_date": "Mar 2025",
            "end_date": "Dic 2025",
            "is_current": False,
            "description": "Analizar información empresarial y financiera de más de 10.000 registros para apoyar la toma de decisiones comerciales, utilizando herramientas de análisis de datos y automatización.",
            "bullets": [
                "Analicé y consolidé bases de datos con más de 10.000 registros utilizando Excel avanzado y Python para limpieza, validación, eliminación de duplicados, filtrado y segmentación de información.",
                "Realicé cruces de información entre fuentes internas y externas (incluyendo fuentes institucionales) para analizar variables empresariales como tamaño de empresa, número de empleados, presupuesto y nivel de endeudamiento, generando indicadores para apoyar decisiones comerciales.",
                "Desarrollé soluciones de automatización con Python y Google Apps Script para agilizar tareas de procesamiento, organización y consolidación de información.",
                "Consulté y realicé seguimiento a un volumen diario de empresas (más de 100 consultadas, cerca de 30 contactadas y entre 30-40 en seguimiento activo), aplicando criterios de análisis de datos para priorizar oportunidades.",
                "Gestioné información relacionada con productos financieros (créditos, CDT, tarjetas de crédito, depósitos y fiducias) de acuerdo con el perfil de cada empresa/cliente, identificado mediante análisis de datos.",
            ],
            "technical_skills": ["Python", "SQL", "Power BI", "Excel", "Pandas", "DAX", "Google Apps Script"],
            "soft_skills": ["Análisis", "Comunicación", "Organización", "Trabajo en equipo"],
        },
        {
            "company": "Banco de Bogotá",
            "title": "Asesor Comercial (Prácticas)",
            "city": "Bogotá, Colombia",
            "modality": "Presencial",
            "start_date": "Oct 2023",
            "end_date": "Oct 2024",
            "is_current": False,
            "description": "Apoyar procesos comerciales y operativos relacionados con clientes, productos financieros y gestión de información.",
            "bullets": [
                "Gestioné y validé información de clientes y productos financieros mediante Excel y plataformas internas, realizando consulta y seguimiento de datos.",
                "Atendí y gestioné clientes, adquiriendo experiencia en productos financieros, operaciones bancarias y procesos comerciales.",
                "Verifiqué información y documentación de clientes, garantizando el cumplimiento de los procedimientos establecidos por la entidad.",
            ],
            "technical_skills": ["Excel", "Plataformas bancarias", "Análisis financiero"],
            "soft_skills": ["Atención al cliente", "Comunicación", "Trabajo en equipo"],
        },
    ],
    "education": [
        {
            "institution": "Universidad Metropolitana de Tecnología",
            "degree": "Ingeniería de Software",
            "level": "bachelor",
            "status": "finished",
            "start_date": "2021-01",
            "end_date": "2025-12",
            "description": (
                "Formación profesional en desarrollo de software, bases de "
                "datos, arquitectura de software, análisis de sistemas y "
                "gestión de proyectos tecnológicos."),
            "technical_skills": ["Python", "SQL", "JavaScript",
                                 "Bases de datos", "Git"],
            "soft_skills": ["Pensamiento lógico", "Trabajo en equipo",
                            "Gestión de proyectos"],
            "perspectives": [
                {
                    "id": "p1",
                    "label": "Ingeniería de software y datos",
                    "description": (
                        "Formación orientada al desarrollo de soluciones "
                        "tecnológicas y procesamiento de información "
                        "mediante herramientas de programación y bases de "
                        "datos."),
                    "skills": ["Programming", "Databases",
                               "Software Engineering"],
                    "tools": ["Python", "SQL", "Git", "JavaScript"],
                    "domains": ["Software Engineering", "Data",
                                "Technology"],
                    "roles": ["Software Engineer", "Data Analyst",
                              "Backend Developer"],
                },
            ],
        },
        {
            "institution": "Instituto Técnico Empresarial de Colombia",
            "degree": "Técnico en Análisis Administrativo y Financiero",
            "level": "technical",
            "status": "finished",
            "start_date": "2019-01",
            "end_date": "2020-12",
            "description": (
                "Formación en procesos administrativos, análisis "
                "financiero, manejo de información empresarial y "
                "herramientas ofimáticas."),
            "technical_skills": ["Excel", "Análisis financiero",
                                 "PowerPoint"],
            "soft_skills": ["Organización", "Atención al detalle"],
            "perspectives": [],
        },
    ],
    "projects": [
        {
            "name": "Retail Intelligence Dashboard",
            "url": "https://andresramirez.dev/projects/retail-intelligence",
            "repo": "https://github.com/andresramirez-dev/retail-intelligence",
            "technologies": ["Python", "Pandas", "NumPy", "Power BI",
                             "SQL", "Excel"],
            "start_date": "2026-02",
            "end_date": "2026-04",
            "description": (
                "Proyecto de análisis de inventario y demanda para "
                "identificar tendencias de ventas, productos con riesgo de "
                "agotamiento y oportunidades de optimización mediante "
                "indicadores y dashboards interactivos."),
            "technical_skills": ["Data Analysis", "Data Visualization",
                                 "Python", "Power BI"],
            "soft_skills": ["Pensamiento analítico",
                            "Resolución de problemas"],
            "perspectives": [
                {
                    "id": "p1",
                    "label": "Business Intelligence",
                    "description": (
                        "Proyecto enfocado en convertir datos operativos en "
                        "indicadores visuales para facilitar el análisis "
                        "empresarial."),
                    "skills": ["BI", "Data Visualization", "KPI Analysis"],
                    "tools": ["Power BI", "Python", "Pandas", "Excel"],
                    "domains": ["Retail", "Inventory",
                                "Business Intelligence"],
                    "roles": ["Data Analyst", "BI Analyst",
                              "Reporting Analyst"],
                },
            ],
        },
        {
            "name": "Currency Analytics API",
            "url": "https://andresramirez.dev/projects/currency-api",
            "repo": "https://github.com/andresramirez-dev/currency-analytics",
            "technologies": ["Python", "FastAPI", "REST API", "Pandas",
                             "JSON"],
            "start_date": "2026-05",
            "end_date": "2026-06",
            "description": (
                "Aplicación para consultar y analizar la variación "
                "histórica de monedas mediante APIs externas, incluyendo "
                "cálculos de variación porcentual y generación de "
                "indicadores financieros."),
            "technical_skills": ["Python", "APIs", "Data Processing"],
            "soft_skills": ["Investigación", "Pensamiento crítico"],
            "perspectives": [
                {
                    "id": "p1",
                    "label": "Automatización financiera",
                    "description": (
                        "Aplicación orientada al procesamiento automatizado "
                        "de información financiera obtenida desde servicios "
                        "externos."),
                    "skills": ["Financial Analysis", "Automation",
                               "API Integration"],
                    "tools": ["Python", "FastAPI", "Pandas"],
                    "domains": ["Finance", "FinTech", "Data"],
                    "roles": ["Python Developer", "Data Analyst",
                              "Financial Data Analyst"],
                },
            ],
        },
    ],
    "certifications": [
        {
            "name": "Microsoft Power BI Data Analyst",
            "institution": "Microsoft",
            "issued_date": "2026-07-15",
            "expiry_date": "2028-07-15",
            "credential_id": "PBI-2026-847291",
            "credential_url": "https://credentials.example.com/PBI-2026-847291",
            "description": (
                "Certificación relacionada con análisis de datos, modelado, "
                "visualización y construcción de reportes empresariales "
                "utilizando Power BI."),
            "technical_skills": ["Power BI", "DAX", "Data Modeling"],
            "soft_skills": ["Análisis", "Comunicación"],
            "perspectives": [
                {
                    "id": "p1",
                    "label": "Business Intelligence",
                    "description": (
                        "Certificación orientada al análisis y visualización "
                        "de información empresarial."),
                    "skills": ["Business Intelligence", "Data Modeling",
                               "Visualization"],
                    "tools": ["Power BI", "DAX"],
                    "domains": ["BI", "Analytics", "Business"],
                    "roles": ["Power BI Analyst", "BI Analyst",
                              "Data Analyst"],
                },
            ],
        },
        {
            "name": "Python for Data Analysis",
            "institution": "DataCamp",
            "issued_date": "2026-05-22",
            "expiry_date": None,
            "credential_id": "DC-PYDA-582941",
            "credential_url": "https://credentials.example.com/DC-PYDA-582941",
            "description": (
                "Certificación de formación práctica en procesamiento, "
                "transformación y análisis de datos utilizando Python y "
                "librerías especializadas."),
            "technical_skills": ["Python", "Pandas", "NumPy"],
            "soft_skills": ["Pensamiento analítico",
                            "Resolución de problemas"],
            "perspectives": [],
        },
    ],
}


def _ensure_guest_demo_flat(db) -> None:
    """Siembra el perfil demo del invitado una sola vez (idempotente)."""
    from app.services.search_profiles import GUEST_OWNER

    if _stored_user_flat(db, GUEST_OWNER):
        return
    allowed = {key: GUEST_DEMO_FLAT.get(key, DEFAULT_PROFILE[key])
               for key in DEFAULT_PROFILE}
    if is_firestore(db):
        from app.database import firestore_repo as fs

        fs.save_user_profile(db, GUEST_OWNER, allowed)
    else:
        db.add(UserProfile(
            uid=GUEST_OWNER, data=json.dumps(allowed, ensure_ascii=False)))
        db.commit()


def _store_user_rich(db, uid: str, normalized: dict) -> None:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        fs.save_user_rich_profile(db, uid, normalized)
    else:
        row = db.query(UserRichProfile).filter(
            UserRichProfile.uid == uid).first()
        if not row:
            row = UserRichProfile(uid=uid, data="{}")
            db.add(row)
        row.data = json.dumps(normalized, ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()


def _ensure_guest_demo_rich(db) -> None:
    """Siembra el perfil estructurado demo una sola vez (idempotente)."""
    from app.profile import schema as profile_schema
    from app.services.search_profiles import GUEST_OWNER

    if _stored_user_rich(db, GUEST_OWNER):
        return
    normalized, _warnings = profile_schema.normalize_rich_profile(
        dict(GUEST_DEMO_RICH))
    _store_user_rich(db, GUEST_OWNER, normalized)


# ---------------------------------------------------------------------------
# Funciones auxiliares de visibilidad por usuario
# ---------------------------------------------------------------------------

def _store_uid(uid: str | None, email: str | None) -> str | None:
    """Devuelve el uid a usar para almacenamiento (invitados comparten GUEST_OWNER)."""
    from app.services.search_profiles import _is_guest, GUEST_OWNER
    if not uid:
        return None
    if _is_guest(uid, email):
        return GUEST_OWNER
    return uid


def _visible_ids(db: Session, uid: str | None, email: str | None) -> set[str]:
    """IDs de ofertas visibles para el usuario (por owner_uid o perfiles)."""
    if not uid:
        return set()
    store_uid = _store_uid(uid, email)
    visible = set()
    # Ofertas del usuario
    if is_firestore(db):
        from app.database import firestore_repo as fs
        for snap in fs._col(db, "jobs").stream():
            data = snap.to_dict()
            if data.get("owner_uid") == store_uid:
                visible.add(snap.id)
    else:
        rows = db.query(Job).filter(Job.owner_uid == store_uid).all()
        for row in rows:
            visible.add(str(row.id))
    # Ofertas encontradas por perfiles del usuario
    from app.services import search_profiles as profiles
    for profile in profiles.list_profiles(db):
        if profile.get("owner_uid") == store_uid:
            pid = str(profile["id"])
            if is_firestore(db):
                from app.database import firestore_repo as fs
                for snap in fs._col(db, "jobs").stream():
                    data = snap.to_dict()
                    pids = data.get("search_profile_ids") or []
                    if pid in pids:
                        visible.add(snap.id)
            else:
                rows = db.query(Job).all()
                for row in rows:
                    pids = _parse_list(getattr(row, "search_profile_ids", None))
                    if pid in pids:
                        visible.add(str(row.id))
    return visible


def _all_user_states(db: Session, store_uid: str | None) -> dict[str, dict]:
    """Estados de oferta por usuario (subcoleccion users/{uid}/job_states)."""
    if not store_uid:
        return {}
    if is_firestore(db):
        from app.database import firestore_repo as fs
        return fs.list_user_job_states(db, store_uid)
    # SQLite: no hay tabla de estados por usuario
    return {}


def _apply_state(record: Record, state: dict | None) -> Record:
    """Aplica el estado del usuario a un record (sin mutar el original)."""
    if not state:
        return record
    record.status = state.get("status") or record.status
    if state.get("discard_reason"):
        record.discard_reason = state.get("discard_reason")
    if state.get("discard_note"):
        record.discard_note = state.get("discard_note")
    if state.get("application_status"):
        record.application_status = state.get("application_status")
    if state.get("decided_at"):
        record.decided_at = state.get("decided_at")
    if state.get("applied_at"):
        record.applied_at = state.get("applied_at")
    return record


def can_view_job(db: Session, job_id: str, uid: str | None, email: str | None) -> bool:
    """Verifica si un usuario puede ver una oferta específica."""
    if not uid:
        return True  # Sin sesión: acceso legado
    store_uid = _store_uid(uid, email)
    job = get_job_by_id(db, job_id)
    if not job:
        return False
    # Verificar si la oferta pertenece al usuario
    if getattr(job, 'owner_uid', None) == store_uid:
        return True
    # Verificar si fue encontrada por un perfil del usuario
    profile_ids = _parse_list(getattr(job, 'search_profile_ids', None))
    if profile_ids:
        from app.services import search_profiles as profiles
        for pid in profile_ids:
            profile = profiles.get_profile(db, pid)
            if profile and profile.get('owner_uid') == store_uid:
                return True
    return False


def _assemble_rich(base_rich: dict, flat: dict) -> dict:
    """Normaliza + valida un perfil estructurado y le pega su plano."""
    from app.profile.perspectives import SECTIONS
    from app.profile.perspectives import validate_profile
    from app.profile import schema as profile_schema

    normalized, schema_warnings = profile_schema.normalize_rich_profile(
        base_rich)
    rich = normalized
    for section in SECTIONS:
        if not isinstance(rich.get(section), list):
            rich[section] = []
    rich["_flat"] = {k: flat.get(k) for k in (
        "full_name", "title", "location", "linkedin", "github", "portfolio",
        "skills", "target_roles", "sectors", "modality",
        "preferred_location", "min_salary", "experience_level",
    )}
    rich["_warnings"] = validate_profile(rich) + schema_warnings
    return rich


def get_rich_profile_for(
    db: Session, uid: str | None, email: str | None
) -> dict:
    """Perfil estructurado segun quien llama. Invitado: demo compartida.
    No-admin con Google: en blanco hasta que guarda; jamas base_cv.json."""
    if not uid or _is_admin(email):
        out = get_rich_profile(db)
        out["scope"] = "admin" if uid else "shared"
        return out
    from app.services.search_profiles import GUEST_OWNER
    from app.services.search_profiles import _is_guest

    if _is_guest(uid, email):
        _ensure_guest_demo_rich(db)
        flat = get_profile_for(db, uid, email)
        out = _assemble_rich(_stored_user_rich(db, GUEST_OWNER), flat)
        out["scope"] = "demo"
        return out
    flat = get_profile_for(db, uid, email)
    out = _assemble_rich(_stored_user_rich(db, uid), flat)
    out["scope"] = "own"
    return out


def save_rich_profile_for(
    db: Session, uid: str | None, email: str | None, data: dict
) -> dict:
    """Guarda el perfil estructurado. No-admin escribe SOLO su registro;
    nunca toca base_cv.json."""
    if not isinstance(data, dict):
        raise ValueError("Perfil invalido: se esperaba un objeto")
    if not uid or _is_admin(email):
        out = save_rich_profile(data)
        out["scope"] = "admin" if uid else "shared"
        return out
    from app.profile.perspectives import SECTIONS
    from app.profile import schema as profile_schema
    from app.profile.perspectives import validate_profile
    from app.services.search_profiles import GUEST_OWNER
    from app.services.search_profiles import _is_guest

    store_uid = GUEST_OWNER if _is_guest(uid, email) else uid
    current = _stored_user_rich(db, store_uid)
    merged = dict(current)
    for key in ("personal", "professional_summary", "skills", "languages",
                "certifications", "target_roles", "technical_skills",
                "soft_skills", "years_experience"):
        if key in data:
            merged[key] = data[key]
    for section in SECTIONS:
        if section in data and isinstance(data[section], list):
            merged[section] = data[section]
    normalized, schema_warnings = profile_schema.normalize_rich_profile(
        merged)
    _store_user_rich(db, store_uid, normalized)
    warnings = validate_profile(normalized) + schema_warnings
    from app.services.search_profiles import _is_guest as _guest_check

    scope = "demo" if _guest_check(uid, email) else "own"
    return {"profile": normalized, "warnings": warnings, "scope": scope}


def backfill_fingerprints(db: Session) -> int:
    """Recalcula huellas con los valores actuales y contadores de grupo.
    Idempotente. Devuelve cuantas filas actualizo."""
    if is_firestore(db):
        from app.database import firestore_repo as fs

        rows = fs.iter_all_jobs(db)
    else:
        rows = [orm_to_record(row) for row in db.query(Job).all()]
    touched = 0
    for job in rows:
        fresh = fingerprint_of(job.title, job.company, job.location)
        if job.fingerprint != fresh or not job.last_seen_at:
            update_job_fields(db, job.id, {
                "fingerprint": fresh,
                "last_seen_at": job.last_seen_at or job.created_at,
            })
            touched += 1
    # Recalcula contadores de todos los grupos.
    seen: set[str] = set()
    for job in iter_all_jobs(db):
        fingerprint = job.fingerprint
        if fingerprint and fingerprint not in seen:
            seen.add(fingerprint)
            count = count_by_fingerprint(db, fingerprint)
            update_fingerprint_group(
                db, fingerprint, {"times_seen": count}
            )
    return touched


def save_analysis(
    db: Session,
    job: Record,
    match_score: float | None,
    matched: list[str] | None = None,
    missing: list[str] | None = None,
    detected_role: str | None = None,
    category: str | None = None,
    evidence: list[str] | None = None,
    experience: str | None = None,
) -> Record:
    """Persiste el resultado de analyze_job. Solo toca campos de
    analisis: nunca decisiones del usuario (status, descartes)."""
    return update_job_fields(db, job.id, {
        "match_score": match_score,
        "matched_skills": matched or [],
        "missing_skills": missing or [],
        "detected_role": detected_role,
        "category": category,
        "evidence": evidence or [],
        "experience_required": experience,
    })


def analyze_pending(db: Session, limit: int = 50) -> dict:
    """Analiza filas con descripcion pero sin score (backfill)."""
    from app.analysis.scorer import analyze_job

    limit = max(1, min(limit, 500))
    profile = get_profile(db)
    rows = get_unscored_jobs(db, limit=limit)
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


def list_applications(db, limit: int = 200, uid: str | None = None) -> list[dict]:
    """Postulaciones con su ultimo evento. En sqlite se derivan de las
    ofertas marcadas como aplicadas (compatibilidad)."""
    if is_firestore(db):
        from app.database import firestore_repo as fs

        apps = fs.list_applications(db, limit=limit, uid=uid)
        for application in apps:
            events = fs.list_application_events(db, application["id"])
            application["events"] = events
            application["last_event"] = events[0] if events else None
        return apps
    applied = get_all_jobs(db, limit=limit, status="applied", uid=uid)
    return [
        {
            "id": f"job-{job.id}",
            "job_id": job.id,
            "company": job.company or "",
            "role": job.detected_role or job.title or "",
            "status": "APPLIED",
            "applied_at": job.applied_at.isoformat()
            if job.applied_at else None,
            "application_url": job.url or "",
            "cv_id": None,
            "notes": f"stage: {job.application_status or 'iniciada'}",
            "events": [],
            "last_event": None,
        }
        for job in applied
    ]


def get_application(db, app_id: str) -> dict | None:
    if is_firestore(db):
        from app.database import firestore_repo as fs

        ref = fs._col(db, "applications").document(str(app_id)).get()
        if not ref.exists:
            return None
        data = ref.to_dict()
        data["id"] = ref.id
        data["events"] = fs.list_application_events(db, ref.id)
        return data
    return None
