"""Perfiles de busqueda automatica (seccion 'Busqueda').

Cada perfil define cargo, ubicacion, modalidad, palabras relacionadas,
fuentes, activo/inactivo y frecuencia. Se persiste en Firestore
(coleccion `search_profiles`) o SQLite (tabla search_profiles).
"""
from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session

from app.database.firestore_client import is_firestore
from app.database.models import SearchProfile
from app.scraper.registry import available_sources


DEFAULT_SOURCES = ["computrabajo", "magneto", "linkedin"]

PROFILE_FIELDS = (
    "name", "title", "location", "modality", "keywords", "sources",
    "active", "frequency_minutes", "max_age_days", "owner_uid", "is_demo",
    "seniority", "experience_years", "salary_min_cop", "contract_types",
)

# Dueño compartido de todo lo demo/test de invitados (anonimos).
GUEST_OWNER = "__guest__"

# Antigüedad maxima permitida en perfiles (dias). 0 = sin limite.
MAX_AGE_DAYS_LIMIT = 60


def _clean_str(value, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _clean_list(value, limit: int = 50) -> list[str]:
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value or [])
    cleaned = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def validate_profile_data(data: dict) -> dict:
    """Normaliza y valida un perfil. Lanza ValueError si es invalido."""
    data = dict(data or {})
    title = _clean_str(data.get("title"))
    if not title:
        raise ValueError("El perfil necesita un cargo objetivo (title).")
    sources = _clean_list(data.get("sources") or DEFAULT_SOURCES)
    known = set(available_sources())
    unknown = [s for s in sources if s not in known]
    if unknown:
        raise ValueError(
            f"Fuentes desconocidas: {', '.join(unknown)}. "
            f"Disponibles: {', '.join(sorted(known))}"
        )
    try:
        frequency = int(data.get("frequency_minutes") or 10)
    except (TypeError, ValueError):
        raise ValueError("frequency_minutes debe ser un entero.")
    frequency = max(5, min(frequency, 1440))
    try:
        max_age = int(data.get("max_age_days") or 0)
    except (TypeError, ValueError):
        raise ValueError("max_age_days debe ser un entero (0 = sin limite).")
    max_age = max(0, min(max_age, MAX_AGE_DAYS_LIMIT))
    owner = data.get("owner_uid")
    owner = str(owner).strip()[:128] or None if owner else None
    from app.services.search_config import validate_fit_fields

    fit = validate_fit_fields(data)
    return {
        "name": _clean_str(data.get("name") or title, 200),
        "title": title,
        "location": _clean_str(data.get("location"), 200) or None,
        "modality": _clean_str(data.get("modality"), 100) or None,
        "keywords": _clean_list(data.get("keywords"), 60),
        "sources": sources,
        "active": bool(data.get("active", True)),
        "frequency_minutes": frequency,
        "max_age_days": max_age,
        "owner_uid": owner,
        "is_demo": 1 if data.get("is_demo") else 0,
        "seniority": fit["seniority"],
        "experience_years": fit["experience_years"],
        "salary_min_cop": fit["salary_min_cop"],
        "salary_max_cop": fit["salary_max_cop"],
        "contract_types": fit["contract_types"],
    }


def _record_to_dict(record_id, data: dict) -> dict:
    keywords = data.get("keywords")
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except ValueError:
            keywords = []
    sources = data.get("sources")
    if isinstance(sources, str):
        try:
            sources = json.loads(sources)
        except ValueError:
            sources = []
    contracts = data.get("contract_types")
    if isinstance(contracts, str):
        try:
            contracts = json.loads(contracts)
        except ValueError:
            contracts = []
    exp = data.get("experience_years")
    salary = data.get("salary_min_cop")
    salary_max = data.get("salary_max_cop")
    return {
        "id": str(record_id),
        "name": data.get("name") or "",
        "title": data.get("title") or "",
        "location": data.get("location"),
        "modality": data.get("modality"),
        "keywords": list(keywords or []),
        "sources": list(sources or []),
        "active": bool(data.get("active", True)),
        "frequency_minutes": int(data.get("frequency_minutes") or 10),
        "max_age_days": int(data.get("max_age_days") or 0),
        "owner_uid": data.get("owner_uid"),
        "is_demo": bool(data.get("is_demo")),
        "seniority": data.get("seniority"),
        "experience_years": exp,
        "salary_min_cop": salary,
        "salary_max_cop": salary_max,
        "contract_types": list(contracts or []),
        "last_run_at": _iso(data.get("last_run_at")),
        "next_run_at": _iso(data.get("next_run_at")),
        "last_run_status": data.get("last_run_status"),
        "last_found": int(data.get("last_found") or 0),
        "last_new": int(data.get("last_new") or 0),
        "last_error": data.get("last_error"),
        "created_at": _iso(data.get("created_at")),
        "updated_at": _iso(data.get("updated_at")),
    }


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _orm_to_dict(row: SearchProfile) -> dict:
    return _record_to_dict(row.id, {
        "name": row.name, "title": row.title, "location": row.location,
        "modality": row.modality, "keywords": row.keywords,
        "sources": row.sources, "active": row.active,
        "frequency_minutes": row.frequency_minutes,
        "max_age_days": getattr(row, "max_age_days", 0) or 0,
        "owner_uid": getattr(row, "owner_uid", None),
        "is_demo": bool(getattr(row, "is_demo", 0)),
        "seniority": getattr(row, "seniority", None),
        "experience_years": getattr(row, "experience_years", None),
        "salary_min_cop": getattr(row, "salary_min_cop", None),
        "salary_max_cop": getattr(row, "salary_max_cop", None),
        "contract_types": getattr(row, "contract_types", None),
        "last_run_at": row.last_run_at, "next_run_at": row.next_run_at,
        "last_run_status": row.last_run_status,
        "last_found": row.last_found, "last_new": row.last_new,
        "last_error": row.last_error, "created_at": row.created_at,
        "updated_at": row.updated_at,
    })


def list_profiles(db: Session) -> list[dict]:
    if is_firestore(db):
        docs = db.collection("search_profiles").stream()
        profiles = [_record_to_dict(d.id, d.to_dict()) for d in docs]
        profiles.sort(key=lambda p: (p["name"] or "").lower())
        return profiles
    rows = db.query(SearchProfile).order_by(SearchProfile.id.asc()).all()
    return [_orm_to_dict(row) for row in rows]


def get_profile(db: Session, profile_id) -> dict | None:
    if is_firestore(db):
        snap = db.collection("search_profiles").document(str(profile_id)).get()
        if not snap.exists:
            return None
        return _record_to_dict(snap.id, snap.to_dict())
    try:
        numeric = int(profile_id)
    except (TypeError, ValueError):
        return None
    row = db.query(SearchProfile).filter(SearchProfile.id == numeric).first()
    return _orm_to_dict(row) if row else None


def create_profile(
    db: Session, data: dict, owner_uid: str | None = None,
    is_demo: bool = False,
) -> dict:
    cleaned = validate_profile_data(data)
    # El dueño lo decide el servidor (sesion), nunca el payload.
    cleaned["owner_uid"] = owner_uid
    cleaned["is_demo"] = 1 if is_demo else 0
    now = datetime.utcnow()
    if is_firestore(db):
        payload = {**cleaned, "created_at": now, "updated_at": now,
                   "next_run_at": now if cleaned["active"] else None}
        _, ref = db.collection("search_profiles").add(payload)
        return get_profile(db, ref.id)
    row = SearchProfile(
        **{**cleaned,
           "keywords": json.dumps(cleaned["keywords"], ensure_ascii=False),
           "sources": json.dumps(cleaned["sources"], ensure_ascii=False),
           "contract_types": json.dumps(
               cleaned["contract_types"], ensure_ascii=False)},
        next_run_at=now if cleaned["active"] else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _orm_to_dict(row)


def update_profile(db: Session, profile_id, data: dict) -> dict | None:
    cleaned = validate_profile_data({**(get_profile(db, profile_id) or {}), **data})
    now = datetime.utcnow()
    if is_firestore(db):
        ref = db.collection("search_profiles").document(str(profile_id))
        if not ref.get().exists:
            return None
        ref.update({**cleaned, "updated_at": now})
        return get_profile(db, profile_id)
    try:
        numeric = int(profile_id)
    except (TypeError, ValueError):
        return None
    row = db.query(SearchProfile).filter(SearchProfile.id == numeric).first()
    if not row:
        return None
    row.name = cleaned["name"]
    row.title = cleaned["title"]
    row.location = cleaned["location"]
    row.modality = cleaned["modality"]
    row.keywords = json.dumps(cleaned["keywords"], ensure_ascii=False)
    row.sources = json.dumps(cleaned["sources"], ensure_ascii=False)
    row.active = 1 if cleaned["active"] else 0
    row.frequency_minutes = cleaned["frequency_minutes"]
    row.max_age_days = cleaned["max_age_days"]
    row.seniority = cleaned["seniority"]
    row.experience_years = cleaned["experience_years"]
    row.salary_min_cop = cleaned["salary_min_cop"]
    row.salary_max_cop = cleaned["salary_max_cop"]
    row.contract_types = json.dumps(
        cleaned["contract_types"], ensure_ascii=False)
    # Si se reactiva sin proxima ejecucion, programarla ya.
    if cleaned["active"] and not row.next_run_at:
        row.next_run_at = now
    db.add(row)
    db.commit()
    db.refresh(row)
    return _orm_to_dict(row)


def delete_profile(db: Session, profile_id) -> bool:
    if is_firestore(db):
        ref = db.collection("search_profiles").document(str(profile_id))
        if not ref.get().exists:
            return False
        ref.delete()
        return True
    try:
        numeric = int(profile_id)
    except (TypeError, ValueError):
        return False
    row = db.query(SearchProfile).filter(SearchProfile.id == numeric).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Visibilidad por usuario. Admin/sin sesion -> todo (historico). Invitado
# (anonimo) -> solo demos (+ lo que cree, que queda como demo compartido).
# Otro usuario -> solo lo suyo (empieza en blanco).
# ---------------------------------------------------------------------------

def _is_admin(email: str | None) -> bool:
    from app.config import is_admin_email

    return is_admin_email(email)


def _is_guest(uid: str | None, email: str | None) -> bool:
    return bool(uid) and not (email or "").strip()


def _guest_owner_uid(uid: str | None, email: str | None) -> str | None:
    """Dueño a asignar al crear: invitados comparten GUEST_OWNER."""
    if not uid:
        return None
    if _is_admin(email):
        return None
    if _is_guest(uid, email):
        return GUEST_OWNER
    return uid


def _visible(profile: dict, uid: str | None, email: str | None) -> bool:
    if not uid or _is_admin(email):
        return True
    if _is_guest(uid, email):
        return bool(profile.get("is_demo")) or (
            profile.get("owner_uid") == GUEST_OWNER)
    return profile.get("owner_uid") == uid


def get_profile_for(
    db: Session, profile_id, uid: str | None, email: str | None
) -> dict | None:
    profile = get_profile(db, profile_id)
    if not profile or not _visible(profile, uid, email):
        return None
    return profile


def list_profiles_for(
    db: Session, uid: str | None, email: str | None
) -> list[dict]:
    if uid and _is_guest(uid, email):
        ensure_guest_demo(db)
    return [p for p in list_profiles(db) if _visible(p, uid, email)]


def create_profile_for(
    db: Session, data: dict, uid: str | None, email: str | None
) -> dict:
    data = {k: v for k, v in (data or {}).items()
            if k not in ("owner_uid", "is_demo")}
    return create_profile(
        db, data, owner_uid=_guest_owner_uid(uid, email))


def update_profile_for(
    db: Session, profile_id, data: dict, uid: str | None, email: str | None
) -> dict | None:
    if not get_profile_for(db, profile_id, uid, email):
        return None
    data = {k: v for k, v in (data or {}).items()
            if k not in ("owner_uid", "is_demo")}
    return update_profile(db, profile_id, data)


def delete_profile_for(
    db: Session, profile_id, uid: str | None, email: str | None
) -> bool:
    if not get_profile_for(db, profile_id, uid, email):
        return False
    # Los CVs de referencia huerfanos se limpian aqui mismo.
    try:
        from app.services import profile_cvs as pcvs

        pcvs.delete_profile_cv(db, profile_id)
    except Exception:  # noqa: BLE001
        pass
    return delete_profile(db, profile_id)


DEMO_PROFILES: tuple[dict, ...] = (
    {
        "name": "Demo – Analista de Datos",
        "title": "Analista de Datos",
        "location": "Bogotá",
        "modality": "Híbrido",
        "keywords": ["Python", "SQL", "Power BI"],
        "frequency_minutes": 60,
        "max_age_days": 30,
        "active": True,
    },
    {
        "name": "Demo – Desarrollador Python",
        "title": "Desarrollador Python",
        "location": "Medellín",
        "modality": "Remoto",
        "keywords": ["Python", "Django", "PostgreSQL"],
        "frequency_minutes": 120,
        "max_age_days": 30,
        "active": True,
    },
)


def ensure_guest_demo(db: Session) -> None:
    """Crea los perfiles demo si no existe ninguno (idempotente)."""
    try:
        if any(p.get("is_demo") for p in list_profiles(db)):
            return
    except Exception:  # noqa: BLE001
        return
    for demo in DEMO_PROFILES:
        try:
            create_profile(db, demo, owner_uid=GUEST_OWNER, is_demo=True)
        except Exception:  # noqa: BLE001
            continue


def touch_run(
    db: Session,
    profile_id,
    *,
    status: str,
    found: int = 0,
    new: int = 0,
    error: str | None = None,
    frequency_minutes: int | None = None,
    now: datetime | None = None,
) -> dict | None:
    """Registra el resultado de una ejecucion y programa la proxima."""
    now = now or datetime.utcnow()
    profile = get_profile(db, profile_id)
    if not profile:
        return None
    frequency = frequency_minutes or profile["frequency_minutes"] or 10
    from datetime import timedelta

    fields = {
        "last_run_at": now,
        "last_run_status": status,
        "last_found": found,
        "last_new": new,
        "last_error": error,
        "next_run_at": now + timedelta(minutes=frequency),
    }
    if is_firestore(db):
        db.collection("search_profiles").document(str(profile_id)).update(fields)
        return get_profile(db, profile_id)
    try:
        numeric = int(profile_id)
    except (TypeError, ValueError):
        return None
    row = db.query(SearchProfile).filter(SearchProfile.id == numeric).first()
    if not row:
        return None
    for key, value in fields.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _orm_to_dict(row)
