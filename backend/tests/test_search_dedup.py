"""Busquedas sin repetir informacion + links guardados + antigüedad.

- Repetir la misma busqueda (mismos links) no crea filas nuevas.
- Los links (url) se persisten tal cual llegan del scraper.
- max_age_days descarta lo viejo antes de guardar.
- El perfil de busqueda valida y persiste max_age_days.
"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.scraper.base import filter_by_max_age, job_posted_at


def _db():
    from app.database.connection import SessionLocal

    return SessionLocal()


def _clean(db, company: str):
    from app.database.models import Job

    db.query(Job).filter(Job.company == company).delete(
        synchronize_session=False)
    db.commit()


def test_repeated_search_does_not_duplicate():
    """Dos 'busquedas' con los mismos links -> mismas filas, sin duplicar."""
    from app.services.job_service import save_jobs

    company = "Empresa NoRepite"
    rows = [
        {"title": f"Cargo {i}", "company": company,
         "url": f"https://example.com/norepite-{i}",
         # Descripcion unica por fila: el hash de contenido no debe
         # fusionarlas (eso lo cubre test_dedup_content_hash).
         "description": f"Oferta numero {i} Python SQL Django {i} " * 20,
         "source": "computrabajo"}
        for i in range(3)
    ]
    db = _db()
    try:
        first = save_jobs(db, rows, search_query="python")
        # Segunda busqueda: mismos links + uno nuevo.
        again = save_jobs(db, rows + [
            {"title": "Cargo nuevo", "company": company,
             "url": "https://example.com/norepite-nuevo",
             "description": "DAX Power BI " * 40,
             "source": "computrabajo"},
        ], search_query="python")
        first_ids = {j.id for j in first}
        again_ids = {j.id for j in again}
        # Los 3 repetidos conservan su id; solo 1 fila es nueva.
        assert first_ids <= again_ids
        assert len(again_ids) == 4
        # Links guardados automaticamente, intactos.
        urls = {j.url for j in again}
        assert "https://example.com/norepite-0" in urls
        assert "https://example.com/norepite-nuevo" in urls
    finally:
        _clean(db, company)
        db.close()


def test_filter_by_max_age():
    now = datetime.utcnow()
    jobs = [
        {"title": "Nueva", "published_at": now - timedelta(hours=5)},
        {"title": "Vieja", "published_at": now - timedelta(days=20)},
        {"title": "Texto viejo", "published_text": "Hace 2 semanas"},
        {"title": "Sin fecha"},
    ]
    fresh = filter_by_max_age(jobs, 7, now=now)
    titles = {j["title"] for j in fresh}
    assert titles == {"Nueva", "Sin fecha"}
    # 0 = sin filtro.
    assert len(filter_by_max_age(jobs, 0, now=now)) == 4
    assert job_posted_at({"title": "x"}) is None


def test_search_endpoint_respects_max_age(monkeypatch):
    """GET /jobs/search con max_age_days filtra antes de guardar."""
    import app.main as main_module

    now = datetime.utcnow()

    class FakeScraper:
        source = "computrabajo"

        def search(self, q, max_pages=1, include_details=False,
                   location=None):
            return [
                {"title": "Oferta fresca", "company": "Empresa Edad",
                 "url": "https://example.com/edad-fresca",
                 "description": "Python fresco unico " * 60,
                 "source": "computrabajo",
                 "published_at": now - timedelta(days=1)},
                {"title": "Oferta vieja", "company": "Empresa Edad",
                 "url": "https://example.com/edad-vieja",
                 "description": "Python viejo unico " * 60,
                 "source": "computrabajo",
                 "published_at": now - timedelta(days=30)},
            ]

    # main.py importa get_scraper por nombre: parchar ahi.
    monkeypatch.setattr(main_module, "get_scraper", lambda s: FakeScraper())
    # Fase 1: endpoints en routers usan registry.get_scraper.
    monkeypatch.setattr(
        "app.scraper.registry.get_scraper", lambda s: FakeScraper())
    with TestClient(app) as client:
        body = client.get("/jobs/search", params={
            "q": "python edad", "pages": 1, "source": "computrabajo",
            "analyze": False, "max_age_days": 7,
        }).json()
        assert body["found"] == 2
        assert body["filtered_out"] == 1
        assert body["saved"] == 1
        assert body["jobs"][0]["url"] == "https://example.com/edad-fresca"
    db = _db()
    try:
        _clean(db, "Empresa Edad")
    finally:
        db.close()


def test_search_profile_max_age_validation_and_roundtrip():
    from app.services import search_profiles as profiles

    cleaned = profiles.validate_profile_data(
        {"title": "Analista", "max_age_days": 999})
    assert cleaned["max_age_days"] == 60
    cleaned = profiles.validate_profile_data({"title": "Analista"})
    assert cleaned["max_age_days"] == 0

    db = _db()
    try:
        created = profiles.create_profile(db, {
            "name": "Perfil Edad Test", "title": "Analista de Datos",
            "max_age_days": 7, "sources": ["computrabajo"],
        })
        assert created["max_age_days"] == 7
        updated = profiles.update_profile(
            db, created["id"], {"max_age_days": 14})
        assert updated["max_age_days"] == 14
        profiles.delete_profile(db, created["id"])
    finally:
        db.close()
