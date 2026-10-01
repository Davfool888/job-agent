"""Siembra las ofertas ficticias A/B/C para probar Adaptar-perfil.

Uso: ..\\.venv\\Scripts\\python.exe scripts/seed_adapt_test_jobs.py
Idempotente: por URL no duplica (usa el dedup normal).
"""
from app.adapt.test_jobs import ensure_adapt_test_jobs
from app.database.connection import SessionLocal


def main() -> None:
    db = SessionLocal()
    try:
        saved = ensure_adapt_test_jobs(db)
        for job in saved:
            print(f"OK {job.id}: {job.title} @ {job.company}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
