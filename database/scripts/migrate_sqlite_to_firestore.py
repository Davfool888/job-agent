"""Migra SQLite (backend/data/job_agent.db) -> Cloud Firestore.

- jobs/ con doc id = id SQLite en zero-padding (conserva orden/compat).
- applied -> crea applications/{id} + evento APPLICATION_CREATED.
- profile (id=1) -> profiles/base.
- counters/jobs.next = max_id + 1 (ids secuenciales futuras).
- Idempotente: omite documentos que ya existen.
Uso: python database/scripts/migrate_sqlite_to_firestore.py [--dry-run]
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.database.connection import SessionLocal  # noqa: E402
from app.database.firestore_client import FirestoreDatabase  # noqa: E402
from app.database import firestore_repo as fs  # noqa: E402
from app.database.models import Job, Profile  # noqa: E402

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
    finally:
        session.close()


def _col_exists(db, doc_id: str) -> bool:
    return db.collection("jobs").document(doc_id).get().exists


if __name__ == "__main__":
    main()
