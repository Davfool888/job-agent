from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL


connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False
    }


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


Base = declarative_base()


def ensure_columns():
    """Migracion ligera para SQLite: agrega a `jobs` las columnas de
    gestion que no existan (la BD actual se creo con el schema viejo y
    `create_all` no altera tablas existentes). Idempotente."""
    wanted = {
        "status": "VARCHAR(50) NOT NULL DEFAULT 'new'",
        "discard_reason": "VARCHAR(200)",
        "discard_note": "TEXT",
        "decided_at": "DATETIME",
        "applied_at": "DATETIME",
        "application_status": "VARCHAR(50)",
        "match_score": "FLOAT",
        "matched_skills": "TEXT",
        "missing_skills": "TEXT",
        "published_text": "VARCHAR(200)",
        "published_at": "DATETIME",
        "fingerprint": "VARCHAR(64)",
        "times_seen": "INTEGER NOT NULL DEFAULT 1",
        "last_seen_at": "DATETIME",
        "detected_role": "VARCHAR(100)",
        "category": "VARCHAR(50)",
        "evidence": "TEXT",
        "discovered_by": "TEXT",
        "experience_required": "VARCHAR(200)",
        "external_id": "VARCHAR(200)",
        "requirements": "TEXT",
        "responsibilities": "TEXT",
        "sector": "VARCHAR(200)",
        "modality": "VARCHAR(100)",
        "salary": "VARCHAR(200)",
        "content_hash": "VARCHAR(64)",
        "cv_generated": "INTEGER NOT NULL DEFAULT 0",
        "cv_path": "VARCHAR(500)",
        "search_profile_ids": "TEXT",
        "found_at": "DATETIME",
        "first_seen_at": "DATETIME",
        "owner_uid": "VARCHAR(128)",
    }
    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "jobs" not in tables:
            return
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
        }
        for column, ddl in wanted.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}"))
        # Perfil de busqueda: antigüedad maxima (0 = sin limite).
        if "search_profiles" in tables:
            existing_sp = {
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(search_profiles)")
                ).fetchall()
            }
            if "max_age_days" not in existing_sp:
                conn.execute(
                    text("ALTER TABLE search_profiles "
                         "ADD COLUMN max_age_days INTEGER NOT NULL DEFAULT 0")
                )
            if "owner_uid" not in existing_sp:
                conn.execute(
                    text("ALTER TABLE search_profiles "
                         "ADD COLUMN owner_uid VARCHAR(128)")
                )
            if "is_demo" not in existing_sp:
                conn.execute(
                    text("ALTER TABLE search_profiles "
                         "ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
                )
            # Filtros de ajuste (fit): jerarquia perfil > global.
            for column, ddl in (
                ("seniority", "VARCHAR(20)"),
                ("experience_years", "FLOAT"),
                ("salary_min_cop", "INTEGER"),
                ("salary_max_cop", "INTEGER"),
                ("contract_types", "TEXT"),
            ):
                if column not in existing_sp:
                    conn.execute(
                        text(f"ALTER TABLE search_profiles "
                             f"ADD COLUMN {column} {ddl}")
                    )
        # Config global de busqueda: columnas nuevas en tablas viejas.
        if "search_configs" in tables:
            existing_sc = {
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(search_configs)")
                ).fetchall()
            }
            for column, ddl in (
                ("seniority", "VARCHAR(20)"),
                ("experience_years", "FLOAT"),
                ("salary_min_cop", "INTEGER"),
                ("salary_max_cop", "INTEGER"),
                ("contract_types", "TEXT"),
            ):
                if column not in existing_sc:
                    conn.execute(
                        text(f"ALTER TABLE search_configs "
                             f"ADD COLUMN {column} {ddl}")
                    )
        # Config de PDF adaptado: columnas nuevas en tablas viejas.
        if "pdf_configs" in tables:
            existing_pdf = {
                row[1]
                for row in conn.execute(
                    text("PRAGMA table_info(pdf_configs)")
                ).fetchall()
            }
            for column, ddl in (
                ("max_projects", "INTEGER NOT NULL DEFAULT 3"),
                ("max_experiences", "INTEGER NOT NULL DEFAULT 3"),
                ("max_bullets", "INTEGER NOT NULL DEFAULT 0"),
                ("profile_length", "VARCHAR(10) NOT NULL DEFAULT 'full'"),
                ("show_soft_skills", "INTEGER NOT NULL DEFAULT 1"),
                ("show_courses", "INTEGER NOT NULL DEFAULT 1"),
                ("show_languages", "INTEGER NOT NULL DEFAULT 1"),
                ("show_links", "INTEGER NOT NULL DEFAULT 1"),
                ("max_pages", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if column not in existing_pdf:
                    conn.execute(
                        text(f"ALTER TABLE pdf_configs "
                             f"ADD COLUMN {column} {ddl}")
                    )


def get_db():
    """Handle de BD segun DB_BACKEND: Session (sqlite) o
    FirestoreDatabase (firestore). El codigo que recibe `db` no debe
    asumir el motor: usa las funciones de app.services.job_service."""
    from app.config import DB_BACKEND

    if DB_BACKEND == "firestore":
        from app.database.firestore_client import FirestoreDatabase

        yield FirestoreDatabase()
        return
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
