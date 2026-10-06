"""Migra SQLite (backend/data/job_agent.db) -> Cloud Firestore.

- jobs/ con doc id = id SQLite en zero-padding (conserva orden/compat).
- applied -> crea applications/{id} + evento APPLICATION_CREATED.
- profile (id=1) -> profiles/base.
- users/ + user_profiles/ + user_rich_profiles/ por uid (datos de
  cada persona: sin esto los perfiles se pierden al cambiar de BD).
- search_profiles/ + pdf_configs/ + search_configs/ (configuracion).
- counters/jobs.next = max_id + 1 (ids secuenciales futuras).
- Idempotente: omite documentos que ya existen.
Uso: python database/scripts/migrate_sqlite_to_firestore.py [--dry-run]
"""
import json
import sys
from datetime import timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.database.connection import SessionLocal  # noqa: E402
from app.database.firestore_client import FirestoreDatabase  # noqa: E402
from app.database import firestore_repo as fs  # noqa: E402
from app.database.models import (  # noqa: E402
    Job, PDFConfig, Profile, SearchConfig, SearchProfile, User,
    UserProfile, UserRichProfile,
)

_LIST_FIELDS = (
    "matched_skills", "missing_skills", "evidence", "discovered_by",
    "requirements", "responsibilities",
)

APP_STAGE_TO_FS = {
    "pendiente": "PLANNED",
    "iniciada": "APPLIED",
    "aplicada": "APPLIED",
    "entrevista": "INTERVIEW",
    "rechazada": "REJECTED",
    "proceso terminado": "CLOSED",
}


def _parse_list(value):
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def row_to_app_dict(row: Job) -> dict:
    data = {}
    for column in row.__table__.columns.keys():
        if column == "id":
            continue
        value = getattr(row, column)
        if column in _LIST_FIELDS:
            value = _parse_list(value)
        data[column] = value
    return data


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    db = FirestoreDatabase()
    session = SessionLocal()
    try:
        rows = session.query(Job).order_by(Job.id.asc()).all()
        print(f"SQLite: {len(rows)} ofertas")
        migrated = skipped = 0
        max_id = 0
        for row in rows:
            max_id = max(max_id, row.id)
            doc_id = str(row.id).zfill(fs.ID_PAD)
            if _col_exists(db, doc_id):
                skipped += 1
                continue
            data = row_to_app_dict(row)
            if not dry_run:
                fs.create_job_row(db, data, doc_id=doc_id)
                if (data.get("status") or "") == "applied":
                    application = fs.create_application(db, {
                        "job_id": doc_id,
                        "company": data.get("company") or "",
                        "role": data.get("detected_role")
                        or data.get("title") or "",
                        "status": "APPLIED",
                        "applied_at": data.get("applied_at"),
                        "application_url": data.get("url") or "",
                        "notes": f"stage sqlite: {data.get('application_status') or ''}",
                    })
                    fs.append_application_event(db, application["id"], {
                        "type": "APPLICATION_CREATED",
                        "from": None,
                        "to": "APPLIED",
                        "notes": "migrado desde SQLite",
                    })
            migrated += 1

        profile_row = session.query(Profile).filter(Profile.id == 1).first()
        profile_migrated = False
        if profile_row:
            try:
                flat = json.loads(profile_row.data or "{}")
            except ValueError:
                flat = {}
            if not dry_run:
                from app.services.job_service import DEFAULT_PROFILE
                fs.save_profile_doc(db, flat, DEFAULT_PROFILE)
            profile_migrated = True

        if not dry_run:
            ref = db.collection("counters").document("jobs")
            snap = ref.get()
            current = snap.get("next") if snap.exists else 1
            ref.set({"next": max(int(current or 1), max_id + 1)})

        print(f"jobs: migrados={migrated} omitidos={skipped} "
              f"perfil={'si' if profile_migrated else 'no'} "
              f"counters.next={max_id + 1}{' (dry-run)' if dry_run else ''}")

        users_m, users_s = _migrate_users(db, session, dry_run)
        print(f"usuarios+perfiles: migrados={users_m} omitidos={users_s}"
              f"{' (dry-run)' if dry_run else ''}")
        sp_m, sp_s = _migrate_search_profiles(db, session, dry_run)
        print(f"search_profiles: migrados={sp_m} omitidos={sp_s}"
              f"{' (dry-run)' if dry_run else ''}")
        cfg_m, cfg_s = _migrate_simple_configs(db, session, dry_run)
        print(f"pdf/search_configs: migrados={cfg_m} omitidos={cfg_s}"
              f"{' (dry-run)' if dry_run else ''}")
    finally:
        session.close()


def _col_exists(db, doc_id: str) -> bool:
    return db.collection("jobs").document(doc_id).get().exists


def _aware(value):
    """datetime naive -> UTC aware (Firestore lo exige)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    except AttributeError:
        return value


def _json_dict(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _migrate_users(db, session, dry_run: bool) -> tuple[int, int]:
    """users/ + user_profiles/ + user_rich_profiles/ por uid."""
    migrated = skipped = 0
    for row in session.query(User).all():
        if db.collection("users").document(row.uid).get().exists:
            skipped += 1
        elif not dry_run:
            fs.save_user(db, row.uid, {
                "email": row.email or "",
                "nombre": row.nombre or "",
                "telefono": row.telefono or "",
                "created_at": _aware(row.created_at),
                "updated_at": _aware(row.updated_at),
            })
            migrated += 1
        else:
            migrated += 1
    for row in session.query(UserProfile).all():
        ref = db.collection("user_profiles").document(row.uid)
        if ref.get().exists:
            skipped += 1
        elif not dry_run:
            ref.set({"data": _json_dict(row.data),
                     "updated_at": _aware(row.updated_at)})
            migrated += 1
        else:
            migrated += 1
    for row in session.query(UserRichProfile).all():
        ref = db.collection("user_rich_profiles").document(row.uid)
        if ref.get().exists:
            skipped += 1
        elif not dry_run:
            ref.set({"profile": _json_dict(row.data),
                     "updated_at": _aware(row.updated_at)})
            migrated += 1
        else:
            migrated += 1
    return migrated, skipped


def _row_to_profile_dict(row: SearchProfile) -> dict:
    data = {}
    for column in row.__table__.columns.keys():
        if column == "id":
            continue
        value = getattr(row, column)
        if column in ("keywords", "sources", "contract_types"):
            if isinstance(value, str):
                try:
                    value = json.loads(value) if value.strip() else []
                except ValueError:
                    value = []
            value = list(value or [])
        data[column] = _aware(value)
    return data


def _migrate_search_profiles(db, session, dry_run: bool) -> tuple[int, int]:
    migrated = skipped = 0
    for row in session.query(SearchProfile).all():
        # Preserva el id numerico para que los links no se rompan.
        ref = db.collection("search_profiles").document(str(row.id))
        if ref.get().exists:
            skipped += 1
            continue
        if not dry_run:
            ref.set(_row_to_profile_dict(row))
        migrated += 1
    return migrated, skipped


def _migrate_simple_configs(db, session, dry_run: bool) -> tuple[int, int]:
    """pdf_configs/ + search_configs/ por uid (mismos campos)."""
    migrated = skipped = 0
    for row in session.query(PDFConfig).all():
        if db.collection("pdf_configs").document(row.uid).get().exists:
            skipped += 1
            continue
        data = {c: _aware(getattr(row, c))
                for c in row.__table__.columns.keys() if c != "uid"}
        if not dry_run:
            fs.save_pdf_config(db, row.uid, data)
        migrated += 1
    for row in session.query(SearchConfig).all():
        if db.collection("search_configs").document(row.uid).get().exists:
            skipped += 1
            continue
        data = {}
        for column in row.__table__.columns.keys():
            if column == "uid":
                continue
            value = getattr(row, column)
            if column == "contract_types" and isinstance(value, str):
                try:
                    value = json.loads(value) if value.strip() else []
                except ValueError:
                    value = []
            data[column] = _aware(value)
        if not dry_run:
            fs.save_search_config(db, row.uid, data)
        migrated += 1
    return migrated, skipped


if __name__ == "__main__":
    main()
