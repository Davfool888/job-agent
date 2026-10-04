"""Fase 4: cola con worker unico, mismo contrato sync + 202 opt-in."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import run_queue as queue

COMPANY = "Empresa Queue Test"


class FakeScraper:
    source = "computrabajo"

    def search(self, query, max_pages=1, include_details=False,
               location=None, on_page=None):
        rows = [{
            "title": f"Analista {query}", "company": COMPANY,
            "location": "Bogota",
            "url": "https://example.com/queue-1",
            "description": "Power BI SQL Excel dashboards " * 20,
            "source": "computrabajo",
        }]
        if on_page:
            on_page(rows, 1)
        return rows

    def get_job_detail(self, url):
        raise AssertionError("sin detalles en tests")


@pytest.fixture()
def fake_registry(monkeypatch):
    import app.scraper.registry as registry

    monkeypatch.setattr(registry, "get_scraper",
                        lambda source: FakeScraper())
    queue.reset_for_tests()
    yield
    queue.reset_for_tests()


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
            SearchProfile.name.like("QueueTest%")).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _make_profile(client):
    r = client.post("/search-profiles", json={
        "name": "QueueTest", "title": "Analista de Datos",
        "sources": ["computrabajo"], "active": True,
        "frequency_minutes": 10,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_run_sync_igual_que_antes(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            r = client.post(f"/search-profiles/{profile['id']}/run")
            assert r.status_code == 200, r.text
            summary = r.json()
            assert summary["found"] >= 1
            assert summary["new"] >= 1
            assert "errors" in summary
            assert client.post(
                f"/search-profiles/{profile['id']}/run").json()["new"] == 0
        finally:
            client.delete(f"/search-profiles/{profile['id']}")


def test_run_wait_false_202_y_polling(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            r = client.post(f"/search-profiles/{profile['id']}/run",
                            params={"wait": False})
            assert r.status_code == 202, r.text
            job_id = r.json()["job_id"]
            deadline = time.time() + 60
            final = None
            while time.time() < deadline:
                poll = client.get(f"/scheduler/jobs/{job_id}")
                if poll.status_code == 200:
                    final = poll.json()
                    break
                assert poll.status_code == 202
                time.sleep(0.5)
            assert final is not None
            assert final["status"] == "done"
            assert final["result"]["found"] >= 1
            assert client.get("/scheduler/jobs").json()["jobs"]
        finally:
            client.delete(f"/search-profiles/{profile['id']}")


def test_tick_sync_y_status_con_cola(fake_registry, clean_db):
    with TestClient(app) as client:
        profile = _make_profile(client)
        try:
            from app.database.connection import SessionLocal
            from app.database.models import SearchProfile
            from datetime import datetime as dt, timedelta

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
            assert any(r["profile_id"] == profile["id"]
                       for r in body["ran"])
            status = client.get("/scheduler/status").json()
            assert "queue" in status
            assert "last_tick" in status
        finally:
            client.delete(f"/search-profiles/{profile['id']}")


def test_coalescencia_misma_clave():
    job1, _ = queue.submit("tick", "tick:global", {}, wait=False)
    job2, _ = queue.submit("tick", "tick:global", {}, wait=False)
    assert job1["job_id"] == job2["job_id"]
    queue.reset_for_tests()
