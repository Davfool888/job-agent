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


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


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


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
