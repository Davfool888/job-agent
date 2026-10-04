"""Repositorio Firestore: implementa TODA la persistencia sobre
Cloud Firestore con documentos dict (sin ORM).

Convenciones (compatibles con database/schema/*.json):
- Colecciones: jobs, applications (+subcoleccion events), cvs,
  profiles (doc `base`), interactions, counters.
- IDs de jobs: numericos secuenciales en cero-padding ("000000000171")
  via counters/jobs, para no romper ordenamientos ni clientes.
- La app trabaja en minusculas/texto libre; aqui se mapea al esquema
  canonico (status UPPER, discard_reason por codigo, modality enum,
  salary objeto) y viceversa al leer.
- Fechas: datetime naive UTC hacia la app (igual que SQLite).
- Listas (skills, evidence...): arrays nativos; la app tambien acepta
  JSON-TEXT (legado SQLite), el schema JobResponse lo tolera.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime
from datetime import timezone

logger = logging.getLogger(__name__)

ID_PAD = 12

APP_TO_FS_STATUS = {
    "new": "NEW",
    "kept": "SAVED",
    "discarded": "DISCARDED",
    "opened": "VIEWED",
    "applied": "APPLIED",
}
FS_TO_APP_STATUS = {v: k for k, v in APP_TO_FS_STATUS.items()}

_DISCARD_MAP = {
    "no coincide con mi perfil": "LOW_MATCH",
    "requiere demasiada experiencia": "REQUIRED_EXPERIENCE",
    "salario": "LOW_SALARY",
    "ubicacion": "LOCATION",
    "modalidad": "MODALITY",
    "tecnologias que no manejo": "MISSING_SKILLS",
    "tipo de cargo": "NOT_INTERESTED",
    "empresa": "NOT_INTERESTED",
    "otro": "OTHER",
}
_DISCARD_REVERSE = {
    "LOW_MATCH": "No coincide con mi perfil",
    "REQUIRED_EXPERIENCE": "Requiere demasiada experiencia",
    "LOW_SALARY": "Salario",
    "LOCATION": "Ubicación",
    "MODALITY": "Modalidad",
    "MISSING_SKILLS": "Tecnologías que no manejo",
    "NOT_INTERESTED": "Otro",
    "DUPLICATE": "Duplicada",
    "OTHER": "Otro",
}

_MODALITY_MAP = {
    "remoto": "REMOTE",
    "remote": "REMOTE",
    "desde casa": "REMOTE",
    "teletrabajo": "REMOTE",
    "home office": "REMOTE",
    "virtual": "REMOTE",
    "hibrido": "HYBRID",
    "hybrid": "HYBRID",
    "hibrida": "HYBRID",
    "presencial": "ONSITE",
    "onsite": "ONSITE",
    "oficina": "ONSITE",
    "presencial y remoto": "HYBRID",
}

APP_STAGE_TO_FS = {
    "pendiente": "PLANNED",
    "iniciada": "APPLIED",
    "aplicada": "APPLIED",
    "entrevista": "INTERVIEW",
    "rechazada": "REJECTED",
    "proceso terminado": "CLOSED",
}


class Record:
    """Registro dict con acceso por atributo (misma ergonomia que el
    modelo ORM para el codigo que lee job.titulo, job.match_score...)."""

    def __init__(self, id: str, data: dict):
        object.__setattr__(self, "id", id)
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

    def __repr__(self) -> str:  # pragma: no cover
        return f"Record(id={self.id!r})"


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        # Reconstruir datetime plano: DatetimeWithNanoseconds con tz
        # removido via .replace() queda en estado roto para reescribir.
        v = value.replace(tzinfo=None) if value.tzinfo else value
        return datetime(v.year, v.month, v.day, v.hour, v.minute,
                        v.second, v.microsecond)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None
    return None


def _norm(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", (text or "").lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(value.split())


def _as_list(value) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _parse_salary_cop(raw: str | None) -> dict | None:
    """Convierte '$6 a $8 millones' -> {min,max,currency}. Si no hay
    patron confiable devuelve None (se guarda igual el raw)."""
    if not raw or not isinstance(raw, str):
        return None
    text = _norm(raw)
    multi = 1_000_000 if ("millon" in text or "millones" in text) else 1
    if "usd" in text or "dolar" in text:
        currency = "USD"
    elif "$" in raw or "cop" in text or "peso" in text or multi > 1:
        currency = "COP"
    else:
        currency = None
    numbers = re.findall(r"\d[\d.,]*", text)
    if not numbers:
        return {"min": None, "max": None, "currency": currency, "raw": raw}

    def to_num(token: str) -> float | None:
        try:
            return float(token.replace(".", "").replace(",", "."))
        except ValueError:
            return None

    values = [to_num(t) for t in numbers]
    values = [v for v in values if v is not None]
    if not values:
        return {"min": None, "max": None, "currency": currency, "raw": raw}
    if len(values) >= 2:
        low, high = values[0] * multi, values[1] * multi
    else:
        low = high = values[0] * multi
    return {"min": low, "max": high, "currency": currency, "raw": raw}


def map_discard_to_code(label: str | None) -> tuple[str | None, str | None]:
    """(codigo, raw). Preserva el texto original en raw."""
    if not label or not str(label).strip():
        return None, None
    raw = str(label).strip()
    return _DISCARD_MAP.get(_norm(raw), "OTHER"), raw


def map_discard_to_label(code: str | None, raw: str | None) -> str | None:
    if raw:
        return raw
    if not code:
        return None
    return _DISCARD_REVERSE.get(code, code)


def map_modality_to_enum(raw: str | None) -> tuple[str | None, str | None]:
    if not raw or not str(raw).strip():
        return None, None
    text = str(raw).strip()
    return _MODALITY_MAP.get(_norm(text)), text


def map_modality_to_label(enum_value: str | None, raw: str | None) -> str:
    labels = {"REMOTE": "Remoto", "HYBRID": "Híbrido", "ONSITE": "Presencial"}
    if raw:
        return raw
    return labels.get(enum_value or "", "")


# ---------------------------------------------------------------------------
# Conversion app-shape <-> documento Firestore
# ---------------------------------------------------------------------------

_APP_FIELDS = (
    "title", "company", "location", "url", "description", "source",
    "search_query", "created_at", "updated_at", "status",
    "discard_reason", "discard_note", "decided_at", "applied_at",
    "application_status", "match_score", "matched_skills",
    "missing_skills", "published_text", "published_at", "fingerprint",
    "times_seen", "last_seen_at", "detected_role", "category",
    "evidence", "discovered_by", "experience_required", "external_id",
    "requirements", "responsibilities", "sector", "modality", "salary",
    "content_hash", "cv_generated", "cv_path",
)


def app_to_fs(data: dict) -> dict:
    """Convierte dict en forma-app a documento Firestore canonico."""
    doc: dict = {}
    doc["title"] = data.get("title") or ""
    doc["published_title"] = data.get("title") or ""
    for key in ("company", "location", "url", "description", "source",
                "search_query", "published_text", "fingerprint",
                "content_hash", "detected_role", "category",
                "experience_required", "external_id", "sector",
                "cv_path"):
        doc[key] = data.get(key)
    doc["source"] = doc["source"] or "computrabajo"
    for key in ("requirements", "responsibilities", "matched_skills",
                "missing_skills", "evidence", "discovered_by",
                "search_profile_ids"):
        doc[key] = _as_list(data.get(key))
    doc["skills"] = _as_list(data.get("skills"))
    doc["technologies"] = _as_list(data.get("technologies"))
    doc["match_score"] = data.get("match_score")
    for key in ("created_at", "updated_at", "decided_at", "applied_at",
                "published_at", "last_seen_at", "found_at",
                "first_seen_at"):
        doc[key] = to_naive(data.get(key))
    doc["times_seen"] = data.get("times_seen") or 1
    doc["cv_generated"] = bool(data.get("cv_generated"))
    doc["status"] = APP_TO_FS_STATUS.get(data.get("status") or "new", "NEW")
    code, raw = map_discard_to_code(data.get("discard_reason"))
    doc["discard_reason"] = code
    doc["discard_reason_raw"] = raw
    doc["discard_note"] = data.get("discard_note")
    doc["discarded_at"] = to_naive(data.get("discarded_at"))
    modality_enum, modality_raw = map_modality_to_enum(data.get("modality"))
    doc["modality"] = modality_enum
    doc["modality_raw"] = modality_raw
    salary = data.get("salary")
    if isinstance(salary, dict):
        doc["salary"] = salary
    else:
        doc["salary"] = _parse_salary_cop(salary)
    doc["viewed"] = bool(data.get("viewed", False))
    doc["view_count"] = data.get("view_count") or 0
    doc["first_viewed_at"] = to_naive(data.get("first_viewed_at"))
    doc["last_viewed_at"] = to_naive(data.get("last_viewed_at"))
    return doc


def fs_to_app(doc_id: str, data: dict) -> Record:
    """Convierte documento Firestore a Record en forma-app."""
    data = dict(data or {})
    app: dict = {}
    app["title"] = data.get("title") or ""
    for key in ("company", "location", "url", "description", "source",
                "search_query", "published_text", "fingerprint",
                "content_hash", "detected_role", "category",
                "experience_required", "external_id", "sector",
                "cv_path"):
        app[key] = data.get(key)
    app["source"] = app["source"] or "computrabajo"
    for key in ("requirements", "responsibilities", "matched_skills",
                "missing_skills", "evidence", "discovered_by",
                "search_profile_ids"):
        app[key] = _as_list(data.get(key))
    app["match_score"] = data.get("match_score")
    for key in ("created_at", "updated_at", "decided_at", "applied_at",
                "published_at", "last_seen_at", "discarded_at",
                "first_viewed_at", "last_viewed_at", "found_at",
                "first_seen_at"):
        app[key] = to_naive(data.get(key))
    app["times_seen"] = data.get("times_seen") or 1
    app["cv_generated"] = bool(data.get("cv_generated"))
    app["status"] = FS_TO_APP_STATUS.get(data.get("status") or "NEW", "new")
    app["discard_reason"] = map_discard_to_label(
        data.get("discard_reason"), data.get("discard_reason_raw")
    )
    app["discard_note"] = data.get("discard_note")
    app["modality"] = map_modality_to_label(
        data.get("modality"), data.get("modality_raw")
    )
    salary = data.get("salary")
    app["salary"] = salary.get("raw", "") if isinstance(salary, dict) else ""
    app["viewed"] = bool(data.get("viewed", False))
    app["view_count"] = data.get("view_count") or 0
    app["application_status"] = data.get("application_status")
    return Record(doc_id, app)


# ---------------------------------------------------------------------------
# Primitivas sobre el handle FirestoreDatabase
# ---------------------------------------------------------------------------

def _col(db, name: str):
    return db.collection(name)


def allocate_job_id(db) -> str:
    """ID secuencial zero-padded via counters/jobs (transaccional)."""
    from google.cloud.firestore_v1 import transactional

    ref = _col(db, "counters").document("jobs")

    @transactional
    def _next(transaction) -> int:
        snap = ref.get(transaction=transaction)
        current = snap.get("next") if snap.exists else 1
        current = int(current or 1)
        transaction.set(ref, {"next": current + 1})
        return current

    return str(_next(db.client.transaction())).zfill(ID_PAD)


def create_job_row(db, data: dict, doc_id: str | None = None) -> Record:
    now = utcnow_naive()
    payload = dict(data)
    payload.setdefault("created_at", now)
    payload.setdefault("updated_at", now)
    payload.setdefault("status", payload.get("status") or "new")
    payload.setdefault("times_seen", 1)
    if doc_id is None:
        doc_id = allocate_job_id(db)
    _col(db, "jobs").document(doc_id).set(app_to_fs(payload))
    return get_job(db, doc_id)


def get_job(db, job_id: str) -> Record | None:
    snap = _col(db, "jobs").document(str(job_id)).get()
    if not snap.exists:
        return None
    return fs_to_app(snap.id, snap.to_dict())


def _first_where(db, field: str, value, extra: dict | None = None):
    from google.cloud.firestore_v1.base_query import FieldFilter

    query = _col(db, "jobs").where(filter=FieldFilter(field, "==", value))
    if extra:
        for key, val in extra.items():
            query = query.where(filter=FieldFilter(key, "==", val))
    for snap in query.limit(1).stream():
        return fs_to_app(snap.id, snap.to_dict())
    return None


def get_by_url(db, url: str) -> Record | None:
    return _first_where(db, "url", url) if url else None


def get_by_external(db, source: str, external_id: str) -> Record | None:
    if not source or not external_id:
        return None
    return _first_where(db, "source", source, {"external_id": external_id})


def get_by_hash(db, content_hash: str) -> Record | None:
    return _first_where(db, "content_hash", content_hash) if content_hash else None


def get_jobs_by_ids(db, ids: list) -> list[Record]:
    records = []
    for job_id in ids:
        record = get_job(db, job_id)
        if record:
            records.append(record)
    return records


def list_jobs(db, limit: int = 200, status: str | None = None,
              since: datetime | None = None) -> list[Record]:
    limit = max(1, min(limit, 500))
    records = []
    for snap in _col(db, "jobs").stream():
        record = fs_to_app(snap.id, snap.to_dict())
        if status and record.status != status:
            continue
        if since:
            ref = record.found_at or record.created_at
            try:
                if ref is None or ref < since:
                    continue
            except TypeError:
                continue
        records.append(record)
    records.sort(key=lambda r: (r.created_at or datetime.min), reverse=True)
    return records[:limit]


def iter_all_jobs(db, limit: int = 5000) -> list[Record]:
    records = [fs_to_app(snap.id, snap.to_dict())
               for snap in _col(db, "jobs").stream()]
    records.sort(key=lambda r: (r.created_at or datetime.min), reverse=True)
    return records[:limit]


def update_job_fields(db, job_or_id, fields: dict) -> Record:
    job_id = job_or_id.id if isinstance(job_or_id, Record) else str(job_or_id)
    ref = _col(db, "jobs").document(job_id)
    snap = ref.get()
    if not snap.exists:
        raise ValueError(f"Oferta {job_id} no encontrada.")
    current = fs_to_app(job_id, snap.to_dict()).to_dict()
    current.pop("id", None)
    current.update({k: v for k, v in fields.items() if k != "id"})
    current["updated_at"] = utcnow_naive()
    ref.set(app_to_fs(current), merge=False)
    return get_job(db, job_id)


def persist_job(db, job: Record) -> Record:
    """Escribe el Record completo (reemplaza db.add+commit)."""
    data = job.to_dict()
    data.pop("id", None)
    data["updated_at"] = utcnow_naive()
    _col(db, "jobs").document(job.id).set(app_to_fs(data), merge=False)
    return get_job(db, job.id)


def refresh_job(db, job: Record) -> Record:
    fresh = get_job(db, job.id)
    if fresh is None:
        raise ValueError(f"Oferta {job.id} no encontrada.")
    return fresh


def delete_job(db, job_id: str) -> bool:
    ref = _col(db, "jobs").document(str(job_id))
    if not ref.get().exists:
        return False
    ref.delete()
    return True


def count_by_fingerprint(db, fingerprint: str) -> int:
    from google.cloud.firestore_v1.base_query import FieldFilter
    if not fingerprint:
        return 0
    return sum(
        1 for _ in _col(db, "jobs").where(filter=FieldFilter("fingerprint", "==", fingerprint)).stream()
    )


def update_fingerprint_group(db, fingerprint: str, fields: dict) -> int:
    from google.cloud.firestore_v1.base_query import FieldFilter
    if not fingerprint:
        return 0
    updated = 0
    for snap in _col(db, "jobs").where(filter=FieldFilter("fingerprint", "==", fingerprint)).stream():
        data = snap.to_dict()
        data.update(fields)
        data["updated_at"] = utcnow_naive()
        snap.reference.set(data)
        updated += 1
    return updated


def tag_discovered(db, ids: list, slug: str) -> None:
    if not ids or not slug:
        return
    for job_id in ids:
        ref = _col(db, "jobs").document(str(job_id))
        snap = ref.get()
        if not snap.exists:
            continue
        current = _as_list(snap.to_dict().get("discovered_by"))
        if slug not in current:
            current.append(slug)
            ref.update({
                "discovered_by": current,
                "updated_at": utcnow_naive(),
            })


def get_unscored_jobs(db, limit: int = 50) -> list[Record]:
    limit = max(1, min(limit, 500))
    out = []
    for record in iter_all_jobs(db, limit=5000):
        if record.match_score is None and (record.description or "").strip():
            out.append(record)
            if len(out) >= limit:
                break
    return out


# ---------------------------------------------------------------------------
# Perfil (profiles/base)
# ---------------------------------------------------------------------------

def get_profile_doc(db) -> dict:
    from app.services.job_service import DEFAULT_PROFILE

    snap = _col(db, "profiles").document("base").get()
    data = dict(snap.to_dict()) if snap.exists else {}
    flat = dict(DEFAULT_PROFILE)
    personal = data.get("personal") or {}
    for key in ("full_name", "title", "location", "linkedin", "github",
                "portfolio"):
        if personal.get(key) is not None:
            flat[key] = personal[key]
    flat["skills"] = list(data.get("legacy_skills_flat") or [])
    flat["target_roles"] = list(data.get("target_roles") or [])
    for key in ("sectors", "modality", "preferred_location", "min_salary",
                "experience_level"):
        if data.get(key) is not None:
            flat[key] = data[key]
    # Secciones ricas + globales (fechas timestamp -> ISO).
    flat["technical_skills"] = list(data.get("technical_skills") or [])
    flat["soft_skills"] = list(data.get("soft_skills") or [])
    flat["years_experience"] = data.get("years_experience")
    flat["personal"] = personal
    flat["professional_summary"] = data.get("summary", "")
    for section in ("experience", "education", "projects", "certifications"):
        flat[section] = _iso_dates(data.get(section) or [])
    flat["languages"] = list(data.get("languages") or [])
    return flat


def _iso_dates(items: list) -> list:
    """datetime (Firestore) -> ISO para consumo JSON/python."""
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        for key in ("start_date", "end_date", "issued_date", "expiry_date"):
            value = item.get(key)
            if hasattr(value, "isoformat"):
                try:
                    item[key] = value.isoformat()[:10]
                except (ValueError, TypeError):
                    item[key] = None
        out.append(item)
    return out


def save_profile_doc(db, data: dict, default_profile: dict) -> dict:
    from app.profile import schema as profile_schema

    allowed = {
        key: data.get(key, default_profile[key]) for key in default_profile
    }
    personal = {
        key: allowed.get(key, "")
        for key in ("full_name", "title", "location", "linkedin",
                    "github", "portfolio")
    }
    # Secciones ricas: se normalizan y las fechas van como timestamp.
    rich, _warnings = profile_schema.normalize_rich_profile(
        {k: data.get(k) for k in (
            "personal", "professional_summary", "years_experience",
            "technical_skills", "soft_skills", "languages", "experience",
            "education", "projects", "certifications", "skills",
            "target_roles",
        ) if k in data}
    )
    doc = {
        "personal": {**personal, **{
            k: v for k, v in (rich.get("personal") or {}).items() if v
        }},
        "summary": rich.get("professional_summary", ""),
        "years_experience": rich.get("years_experience"),
        "technical_skills": rich.get("technical_skills", []),
        "soft_skills": rich.get("soft_skills", []),
        "education": _with_timestamps(rich.get("education", [])),
        "experience": _with_timestamps(rich.get("experience", [])),
        "projects": _with_timestamps(rich.get("projects", [])),
        "certifications": _with_timestamps(rich.get("certifications", [])),
        "languages": rich.get("languages", []),
        "skills": {"programming": [], "data": [], "bi": [],
                   "databases": [], "tools": []},
        "target_roles": list(allowed.get("target_roles") or []),
        "legacy_skills_flat": list(allowed.get("skills") or []),
        "sectors": allowed.get("sectors") or [],
        "modality": allowed.get("modality") or "",
        "preferred_location": allowed.get("preferred_location") or "",
        "min_salary": allowed.get("min_salary") or "",
        "experience_level": allowed.get("experience_level") or "",
        "updated_at": utcnow_naive(),
    }
    # Une grupos de skills legacy si vienen en data["skills"] dict.
    if isinstance(data.get("skills"), dict):
        for group, items in data["skills"].items():
            if group in doc["skills"] and isinstance(items, list):
                doc["skills"][group] = items
    _col(db, "profiles").document("base").set(doc)
    return get_profile_doc(db)


def _with_timestamps(items: list) -> list:
    """Convierte *_date (ISO) a datetime para Firestore (timestamp)."""
    from datetime import datetime as _datetime

    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        for key in ("start_date", "end_date", "issued_date", "expiry_date"):
            value = item.get(key)
            if isinstance(value, str) and value:
                try:
                    item[key] = _datetime.fromisoformat(value)
                except ValueError:
                    item[key] = None
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Postulaciones + eventos + CVs + interacciones
# ---------------------------------------------------------------------------

def find_application_by_job(
    db, job_id: str, uid: str | None = None
) -> dict | None:
    from google.cloud.firestore_v1.base_query import FieldFilter
    query = _col(db, "applications").where(filter=FieldFilter("job_id", "==", str(job_id)))
    if uid:
        query = query.where(filter=FieldFilter("uid", "==", str(uid)))
    query = query.limit(1)
    for snap in query.stream():
        data = snap.to_dict()
        data["id"] = snap.id
        return data
    return None


def create_application(db, payload: dict) -> dict:
    now = utcnow_naive()
    payload = dict(payload)
    payload.setdefault("status", "APPLIED")
    payload.setdefault("created_at", now)
    payload.setdefault("updated_at", now)
    _, ref = _col(db, "applications").add(payload)
    snap = ref.get()
    data = snap.to_dict()
    data["id"] = ref.id
    return data


def update_application(db, app_id: str, fields: dict) -> dict | None:
    ref = _col(db, "applications").document(str(app_id))
    snap = ref.get()
    if not snap.exists:
        return None
    fields = dict(fields)
    fields["updated_at"] = utcnow_naive()
    ref.update(fields)
    data = ref.get().to_dict()
    data["id"] = ref.id
    return data


def append_application_event(db, app_id: str, event: dict) -> str:
    event = dict(event)
    event.setdefault("date", utcnow_naive())
    _, ref = (
        _col(db, "applications")
        .document(str(app_id))
        .collection("events")
        .add(event)
    )
    return ref.id


def list_application_events(db, app_id: str) -> list[dict]:
    events = []
    query = (
        _col(db, "applications")
        .document(str(app_id))
        .collection("events")
        .order_by("date", direction="DESCENDING")
    )
    for snap in query.stream():
        data = snap.to_dict()
        data["id"] = snap.id
        data["date"] = to_naive(data.get("date"))
        events.append(data)
    return events


def list_applications(db, limit: int = 200, uid: str | None = None) -> list[dict]:
    from google.cloud.firestore_v1.base_query import FieldFilter

    limit = max(1, min(limit, 500))
    apps = []
    query = _col(db, "applications")
    if uid:
        query = query.where(filter=FieldFilter("uid", "==", str(uid)))
    for snap in query.stream():
        data = snap.to_dict()
        data["id"] = snap.id
        for key in ("created_at", "updated_at", "applied_at"):
            data[key] = to_naive(data.get(key))
        apps.append(data)
    apps.sort(key=lambda a: (a.get("updated_at") or datetime.min), reverse=True)
    return apps[:limit]


# ---------------------------------------------------------------------------
# Estados de oferta por usuario (subcoleccion users/{uid}/job_states).
# ---------------------------------------------------------------------------

_JOB_STATE_FIELDS = (
    "status", "discard_reason", "discard_note", "application_status",
    "decided_at", "applied_at",
)


def _states_col(db, uid: str):
    return db.collection("users").document(str(uid)).collection("job_states")


def get_user_job_state(db, uid: str, job_id) -> dict | None:
    snap = _states_col(db, uid).document(str(job_id)).get()
    if not snap.exists:
        return None
    data = dict(snap.to_dict() or {})
    out = {key: data.get(key) for key in _JOB_STATE_FIELDS}
    for key in ("decided_at", "applied_at"):
        value = out.get(key)
        out[key] = value.isoformat() if hasattr(value, "isoformat") else value
    if not out.get("status"):
        out["status"] = "new"
    return out


def save_user_job_state(db, uid: str, job_id, fields: dict) -> dict:
    ref = _states_col(db, uid).document(str(job_id))
    snap = ref.get()
    current = dict(snap.to_dict() or {}) if snap.exists else {}
    merged = {**current,
              **{k: v for k, v in (fields or {}).items()
                 if k in _JOB_STATE_FIELDS}}
    merged.setdefault("status", "new")
    merged["updated_at"] = utcnow_naive()
    ref.set(merged, merge=True)
    return get_user_job_state(db, uid, job_id) or dict(merged)


def list_user_job_states(db, uid: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for snap in _states_col(db, uid).stream():
        state = get_user_job_state(db, uid, snap.id)
        if state:
            out[str(snap.id)] = state
    return out


def register_cv_version(db, job_id: str, meta: dict) -> dict:
    from google.cloud.firestore_v1.base_query import FieldFilter
    existing = [
        snap for snap in _col(db, "cvs").where(filter=FieldFilter("job_id", "==", str(job_id))).stream()
    ]
    version = len(existing) + 1
    payload = {
        "job_id": str(job_id),
        "application_id": meta.get("application_id"),
        "version": version,
        "file_name": meta.get("file_name", f"cv_v{version}.pdf"),
        "pdf_path": meta.get("pdf_path"),
        "tex_path": meta.get("tex_path"),
        "generated_at": utcnow_naive(),
        "skills_selected": list(meta.get("skills_selected") or []),
        "experience_selected": list(meta.get("experience_selected") or []),
        "projects_selected": list(meta.get("projects_selected") or []),
        "profile_version": meta.get("profile_version") or "",
        "match_score": meta.get("match_score"),
        "status": "GENERATED",
    }
    _, ref = _col(db, "cvs").add(payload)
    data = ref.get().to_dict()
    data["id"] = ref.id
    data["generated_at"] = to_naive(data.get("generated_at"))
    return data


def list_cvs_for_job(db, job_id: str) -> list[dict]:
    from google.cloud.firestore_v1.base_query import FieldFilter
    out = []
    query = (
        _col(db, "cvs")
        .where(filter=FieldFilter("job_id", "==", str(job_id)))
        .order_by("version", direction="DESCENDING")
    )
    for snap in query.stream():
        data = snap.to_dict()
        data["id"] = snap.id
        data["generated_at"] = to_naive(data.get("generated_at"))
        out.append(data)
    return out


def log_interaction(db, type: str, job_id=None, application_id=None,
                    metadata: dict | None = None) -> str | None:
    """Append-only. Solo Firestore (SQLite no tiene esta tabla)."""
    payload = {
        "user_id": "default",
        "job_id": str(job_id) if job_id is not None else None,
        "application_id": (str(application_id)
                           if application_id is not None else None),
        "type": type,
        "timestamp": utcnow_naive(),
        "metadata": dict(metadata or {}),
    }
    _, ref = _col(db, "interactions").add(payload)
    return ref.id


# ---------------------------------------------------------------------------
# Agregados (Analytics Agent los consume via iter_all_jobs; summarize aqui
# para paridad exacta con la version SQLite)
# ---------------------------------------------------------------------------

def summarize(db) -> dict:
    from collections import Counter

    rows = iter_all_jobs(db)
    total = len(rows)
    by_status: Counter = Counter()
    scored = 0
    score_sum = 0.0
    companies: Counter = Counter()
    queries: Counter = Counter()
    reasons: Counter = Counter()
    categories: Counter = Counter()
    sources: Counter = Counter()
    discovery_counter: Counter = Counter()
    skill_counter: Counter = Counter()
    missing_counter: Counter = Counter()
    hidden_title_relevant = 0
    hidden_title_total = 0
    cv_count = 0

    for row in rows:
        status = row.status or "new"
        by_status[status] += 1
        if row.match_score is not None:
            scored += 1
            score_sum += row.match_score
        if (row.company or "").strip():
            companies[row.company] += 1
        if row.search_query:
            queries[row.search_query] += 1
        if status == "discarded" and row.discard_reason:
            reasons[row.discard_reason] += 1
        categories[row.category or "SIN_ANALIZAR"] += 1
        sources[row.source or "desconocida"] += 1
        for item in _as_list(row.discovered_by):
            if isinstance(item, str) and item.strip():
                discovery_counter[item] += 1
        for item in _as_list(row.matched_skills):
            if isinstance(item, str) and item.strip():
                skill_counter[item] += 1
        for item in _as_list(row.missing_skills):
            if isinstance(item, str) and item.strip():
                missing_counter[item] += 1
        if (row.match_score or 0) >= 40 or (
            row.category and row.category != "OTHER"
        ):
            hidden_title_total += 1
            title_norm = (row.title or "").lower()
            if (
                "analista de datos" not in title_norm
                and "data analyst" not in title_norm
            ):
                hidden_title_relevant += 1
        if row.cv_generated:
            cv_count += 1

    last = rows[0] if rows else None
    return {
        "total": total,
        "by_status": dict(by_status),
        "scored_count": scored,
        "avg_match": round(score_sum / scored, 1) if scored else None,
        "top_companies": [
            {"company": company, "count": count}
            for company, count in companies.most_common(10)
        ],
        "top_queries": [
            {"query": query, "count": count}
            for query, count in queries.most_common(10)
        ],
        "discard_reasons": [
            {"reason": reason, "count": count}
            for reason, count in reasons.most_common()
        ],
        "by_category": dict(categories),
        "by_source": dict(sources),
        "top_discovery_queries": [
            {"query": query, "count": count}
            for query, count in discovery_counter.most_common(15)
        ],
        "top_skills": [
            {"skill": skill, "count": count}
            for skill, count in skill_counter.most_common(15)
        ],
        "top_missing_skills": [
            {"skill": skill, "count": count}
            for skill, count in missing_counter.most_common(15)
        ],
        "relevant_hidden_title": hidden_title_relevant,
        "relevant_total": hidden_title_total,
        "cv_generated_count": cv_count,
        "last_job": (
            {
                "id": last.id,
                "title": last.title,
                "company": last.company,
                "created_at": last.created_at.isoformat()
                if last.created_at
                else None,
            }
            if last
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Usuarios (login con Google). Solo uid/email/nombre/telefono.
# ---------------------------------------------------------------------------

def get_user(db, uid: str) -> dict | None:
    snap = _col(db, "users").document(str(uid)).get()
    if not snap.exists:
        return None
    data = dict(snap.to_dict() or {})
    out = {
        "uid": str(uid),
        "email": data.get("email") or "",
        "nombre": data.get("nombre") or "",
        "telefono": data.get("telefono") or "",
    }
    for key in ("created_at", "updated_at"):
        value = data.get(key)
        out[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return out


def save_user(db, uid: str, fields: dict) -> dict:
    ref = _col(db, "users").document(str(uid))
    snap = ref.get()
    current = dict(snap.to_dict() or {}) if snap.exists else {}
    merged = {**current, **{k: v for k, v in fields.items() if v is not None}}
    merged.setdefault("email", "")
    merged.setdefault("nombre", "")
    merged.setdefault("telefono", "")
    ref.set(merged, merge=True)
    return get_user(db, uid) or {"uid": str(uid), **merged}


# ---------------------------------------------------------------------------
# Perfiles propios por usuario (no-admin). El admin usa el perfil global.
# ---------------------------------------------------------------------------

def get_user_profile(db, uid: str) -> dict:
    """Perfil plano propio ({campo: valor}). Vacio si nunca guardo."""
    snap = _col(db, "user_profiles").document(str(uid)).get()
    if not snap.exists:
        return {}
    data = (snap.to_dict() or {}).get("data") or {}
    return dict(data) if isinstance(data, dict) else {}


def save_user_profile(db, uid: str, data: dict) -> dict:
    ref = _col(db, "user_profiles").document(str(uid))
    ref.set({"data": dict(data or {}), "updated_at": utcnow_naive()},
            merge=True)
    return get_user_profile(db, uid)


def get_user_rich_profile(db, uid: str) -> dict:
    """Perfil estructurado propio. Vacio si nunca guardo."""
    snap = _col(db, "user_rich_profiles").document(str(uid)).get()
    if not snap.exists:
        return {}
    data = (snap.to_dict() or {}).get("profile") or {}
    return dict(data) if isinstance(data, dict) else {}


def save_user_rich_profile(db, uid: str, profile: dict) -> dict:
    ref = _col(db, "user_rich_profiles").document(str(uid))
    ref.set({"profile": dict(profile or {}), "updated_at": utcnow_naive()},
            merge=True)
    return get_user_rich_profile(db, uid)


# ---------------------------------------------------------------------------
# CVs de referencia por perfil de busqueda (solo metadatos; el PDF y el
# texto viven en disco: data/profile_cvs/profile_<id>/{cv.pdf,cv.txt}).
# ---------------------------------------------------------------------------

def get_profile_cv(db, profile_id) -> dict | None:
    snap = _col(db, "profile_cvs").document(str(profile_id)).get()
    if not snap.exists:
        return None
    data = dict(snap.to_dict() or {})
    return {
        "filename": data.get("filename") or "cv.pdf",
        "size_bytes": int(data.get("size_bytes") or 0),
        "pages": int(data.get("pages") or 0),
        "chars": int(data.get("chars") or 0),
        "uploaded_at": data.get("uploaded_at"),
    }


def save_profile_cv(db, profile_id, meta: dict) -> dict:
    ref = _col(db, "profile_cvs").document(str(profile_id))
    ref.set({**dict(meta or {}), "updated_at": meta.get("uploaded_at")},
            merge=True)
    return get_profile_cv(db, profile_id)


def delete_profile_cv(db, profile_id) -> bool:
    ref = _col(db, "profile_cvs").document(str(profile_id))
    if not ref.get().exists:
        return False
    ref.delete()
    return True


# ---------------------------------------------------------------------------
# PDF configs por usuario (Fase 2). Coleccion pdf_configs/{uid}, mismos
# campos que el modelo SQLite (section_order como JSON string, flags 0/1).
# ---------------------------------------------------------------------------

def get_pdf_config(db, uid: str) -> dict | None:
    snap = _col(db, "pdf_configs").document(str(uid)).get()
    if not snap.exists:
        return None
    return dict(snap.to_dict() or {})


def save_pdf_config(db, uid: str, fields: dict) -> dict:
    ref = _col(db, "pdf_configs").document(str(uid))
    snap = ref.get()
    current = dict(snap.to_dict() or {}) if snap.exists else {}
    merged = {**current, **{k: v for k, v in fields.items() if v is not None}}
    ref.set(merged, merge=True)
    return get_pdf_config(db, uid) or {"uid": str(uid), **merged}


def delete_pdf_config(db, uid: str) -> bool:
    ref = _col(db, "pdf_configs").document(str(uid))
    if not ref.get().exists:
        return False
    ref.delete()
    return True
