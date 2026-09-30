"""Busqueda automatica: perfiles, scheduler, dedup y ofertas nuevas.

Usa scraper falso (sin red) y la BD sqlite de desarrollo con limpieza.
"""
from datetime import datetime
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app

COMPANY = "Empresa Scheduler Test"


class FakeScraper:
    source = "computrabajo"

    def search(self, query, max_pages=1, include_details=False):
        base = "https://example.com/scheduler"
        return [
            {
                "title": f"Analista de Datos {query}",
                "company": COMPANY,
                "location": "Bogota",
                "url": f"{base}/datos",
                "description": (
                    "Buscamos analista de datos con Power BI, SQL y Excel "
                    "avanzado para generar dashboards e indicadores."
                ),
                "source": "computrabajo",
            },
            {
                "title": f"Vendedor {query}",
                "company": COMPANY,
                "location": "Bogota",
                "url": f"{base}/ventas",
                "description": "Ventas puerta a puerta. Requisito: moto.",
                "source": "computrabajo",
            },
        ]

    def get_job_detail(self, url):
        raise AssertionError("no deberia pedir detalles en tests")


@pytest.fixture()
def fake_registry(monkeypatch):
    import app.scraper.registry as registry

    monkeypatch.setattr(registry, "get_scraper", lambda source: FakeScraper())
    yield


@pytest.fixture()
def clean_db():
    from app.database.connection import SessionLocal
    from app.database.models import Job, SearchProfile

    yield
    db = SessionLocal()
    try:
        db.query(Job).filter(Job.company == COMPANY).delete(
            synchronize_session=False)
        db.query(SearchProfile).filter(
            SearchProfile.name.like("SchedTest%")).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _make_profile(client, **overrides):
    payload = {
        "name": "SchedTest Analista",
        "title": "Analista de Datos",
        "location": "Bogota",
        "keywords": ["Power BI"],
        "sources": ["computrabajo"],
        "active": True,
        "frequency_minutes": 10,
    }
    payload.update(overrides)
    response = client.post("/search-profiles", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_crud_perfiles():
    with TestClient(app) as client:
        created = _make_profile(client)
        try:
            assert created["active"] is True
            assert created["next_run_at"] is not None

            fetched = client.get(f"/search-profiles/{created['id']}").json()
            assert fetched["title"] == "Analista de Datos"

            updated = client.put(
                f"/search-profiles/{created['id']}",
                json={"frequency_minutes": 30, "active": False},
            ).json()
            assert updated["frequency_minutes"] == 30
            assert updated["active"] is False

            bad = client.post("/search-profiles", json={"title": ""})
            assert bad.status_code == 400
            bad2 = client.post("/search-profiles",
                               json={"title": "X", "sources": ["noexiste"]})
            assert bad2.status_code == 400
            assert client.get("/search-profiles/999999").status_code == 404
        finally:
            client.delete(f"/search-profiles/{created['id']}")


def test_run_manual_crea_nuevas_y_analiza(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            response = client.post(f"/search-profiles/{profile['id']}/run")
            assert response.status_code == 200, response.text
            summary = response.json()
            # 2 queries x 2 ofertas (titulo + 1 keyword).
            assert summary["found"] == 4
            assert summary["new"] == 2
            assert summary["analyzed"] >= 2

            jobs = client.get("/jobs", params={"limit": 200}).json()
            mine = [j for j in jobs
                    if j["company"] == COMPANY]
            assert len(mine) == 2
            for job in mine:
                assert job["status"] == "new"
                assert profile["id"] in job["search_profile_ids"]
                assert job["found_at"] is not None
                assert job["first_seen_at"] is not None
                assert job["match_score"] is not None
        finally:
            client.delete(f"/search-profiles/{profile['id']}")


def test_segunda_ejecucion_no_duplica(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            first = client.post(
                f"/search-profiles/{profile['id']}/run").json()
            assert first["new"] == 2
            second = client.post(
                f"/search-profiles/{profile['id']}/run").json()
            assert second["new"] == 0
            assert second["found"] == 4

            jobs = client.get("/jobs", params={"limit": 200}).json()
            mine = [j for j in jobs if j["company"] == COMPANY]
            assert len(mine) == 2
        finally:
            client.delete(f"/search-profiles/{profile['id']}")


def test_varios_perfiles_comparten_oferta(fake_registry, clean_db):
    with TestClient(app) as client:
        first = _make_profile(client, name="SchedTest Uno")
        second = _make_profile(client, name="SchedTest Dos",
                               title="Data Engineer")
        try:
            client.post(f"/search-profiles/{first['id']}/run")
            client.post(f"/search-profiles/{second['id']}/run")
            jobs = client.get("/jobs", params={"limit": 200}).json()
            mine = [j for j in jobs if j["company"] == COMPANY]
            assert len(mine) == 2
            for job in mine:
                assert first["id"] in job["search_profile_ids"]
                assert second["id"] in job["search_profile_ids"]
        finally:
            client.delete(f"/search-profiles/{first['id']}")
            client.delete(f"/search-profiles/{second['id']}")


def test_run_due_respeta_activos_y_futuros(fake_registry, clean_db):
    from app.scheduler import run_due_profiles

    with TestClient(app):
        from app.database.connection import SessionLocal

        db = SessionLocal()
        try:
            from app.services import search_profiles as profiles

            due = profiles.create_profile(db, {
                "name": "SchedTest Due", "title": "Analista de Datos",
                "sources": ["computrabajo"], "active": True,
                "frequency_minutes": 10,
            })
            # Vencido a proposito.
            from datetime import datetime as dt

            from app.database.models import SearchProfile

            row = db.query(SearchProfile).filter(
                SearchProfile.id == int(due["id"])).first()
            row.next_run_at = dt.utcnow() - timedelta(minutes=1)
            db.add(row)
            db.commit()

            paused = profiles.create_profile(db, {
                "name": "SchedTest Paused", "title": "Otro",
                "sources": ["computrabajo"], "active": False,
                "frequency_minutes": 10,
            })
            result = run_due_profiles(db=db)
            ran = {r["profile_id"] for r in result["ran"]}
            assert due["id"] in ran
            assert paused["id"] not in ran
        finally:
            for pid in (due["id"], paused["id"]):
                profiles.delete_profile(db, pid)
            from app.database.models import Job

            db.query(Job).filter(Job.company == COMPANY).delete(
                synchronize_session=False)
            db.commit()
            db.close()


def test_overlap_guard_omite_en_ejecucion(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            from app.database.connection import SessionLocal
            from app.database.models import SearchProfile

            db = SessionLocal()
            try:
                row = db.query(SearchProfile).filter(
                    SearchProfile.id == int(profile["id"])).first()
                from datetime import datetime as dt

                row.last_run_status = "running"
                row.last_run_at = dt.utcnow()
                db.add(row)
                db.commit()
            finally:
                db.close()
            response = client.post(
                f"/search-profiles/{profile['id']}/run").json()
            assert response["new"] == 0
            assert any("omitido" in e for e in response["errors"])
        finally:
            client.delete(f"/search-profiles/{profile['id']}")


def test_since_filter(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            client.post(f"/search-profiles/{profile['id']}/run")
            future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
            assert client.get("/jobs",
                              params={"since": future}).json() == []
            past = "2000-01-01T00:00:00"
            mine = [j for j in client.get(
                "/jobs", params={"since": past}).json()
                if j["company"] == COMPANY]
            assert len(mine) == 2
            bad = client.get("/jobs", params={"since": "no-fecha"})
            assert bad.status_code == 400
        finally:
            client.delete(f"/search-profiles/{profile['id']}")


def test_scheduler_status_endpoint():
    with TestClient(app) as client:
        body = client.get("/scheduler/status").json()
        assert "enabled" in body
        assert "interval_seconds" in body
        assert "last_tick" in body


def test_scheduler_tick_endpoint(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            from app.database.connection import SessionLocal
            from app.database.models import SearchProfile
            from datetime import datetime as dt

            db = SessionLocal()
            try:
                row = db.query(SearchProfile).filter(
                    SearchProfile.id == int(profile["id"])).first()
                row.next_run_at = dt.utcnow() - timedelta(minutes=1)
                db.add(row)
                db.commit()
            finally:
                db.close()
            body = client.post("/scheduler/tick").json()
            assert any(r["profile_id"] == profile["id"] for r in body["ran"])
        finally:
            client.delete(f"/search-profiles/{profile['id']}")
