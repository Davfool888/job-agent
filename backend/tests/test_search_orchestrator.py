"""Fase 3: orquestador comparte pipeline + breaker sin cambiar resultados."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import search_orchestrator as orch


@pytest.fixture(autouse=True)
def _clean_breaker():
    orch.reset_circuit()
    yield
    orch.reset_circuit()


class _Fail:
    source = "falsa"
    calls = 0

    def search(self, *a, **k):
        type(self).calls += 1
        raise RuntimeError("caida")


class _BadInput:
    source = "falsa"

    def search(self, *a, **k):
        raise ValueError("query invalida")


def test_breaker_abre_tras_fallos_y_se_recupera(monkeypatch):
    monkeypatch.setattr(orch, "FAILURE_THRESHOLD", 3)
    monkeypatch.setattr(orch, "OPEN_SECONDS", 60)
    scraper = _Fail()
    _Fail.calls = 0
    for _ in range(3):
        with pytest.raises(RuntimeError):
            orch.scrape_with(scraper, "falsa", "python")
    assert _Fail.calls == 3
    # 4ta: abre sin golpear la red.
    with pytest.raises(orch.CircuitOpen):
        orch.scrape_with(scraper, "falsa", "python")
    assert _Fail.calls == 3
    orch.reset_circuit("falsa")

    class _Ok:
        source = "falsa"

        def search(self, *a, **k):
            return [{"title": "x"}]

    assert orch.scrape_with(_Ok(), "falsa", "python") == [{"title": "x"}]


def test_valueerror_no_dispara_breaker(monkeypatch):
    monkeypatch.setattr(orch, "FAILURE_THRESHOLD", 3)
    for _ in range(5):
        with pytest.raises(ValueError):
            orch.scrape_with(_BadInput(), "falsa", "python")
    # El breaker sigue cerrado: un fallo real aun golpea la red.
    with pytest.raises(RuntimeError):
        orch.scrape_with(_Fail(), "falsa", "python")


def test_filtros_igual_que_antes():
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    jobs = [
        {"title": "nueva", "published_at": now - timedelta(days=1)},
        {"title": "vieja", "published_at": now - timedelta(days=30)},
        {"title": "sin fecha"},
    ]
    assert len(orch.filter_by_age(jobs, 0)) == 3
    assert len(orch.filter_by_age(jobs, 7)) == 2
    batch = orch.filter_batch(
        [{"title": "a", "location": "Bogotá"},
         {"title": "b", "location": "Medellín"}],
        "bogota", 0)
    assert [j["title"] for j in batch] == ["a"]


def test_rest_contrat_shape_con_orquestador(monkeypatch):
    from datetime import datetime

    now = datetime

    class FakeScraper:
        source = "computrabajo"

        def search(self, q, max_pages=1, include_details=False,
                   location=None, on_page=None):
            rows = [{
                "title": "Dev Fase3", "company": "Empresa F3",
                "url": "https://example.com/fase3-1",
                "description": "Python unico fase3 " * 60,
                "source": "computrabajo",
                "published_at": now.utcnow(),
            }]
            if on_page:
                on_page(rows, 1)
            return rows

    monkeypatch.setattr(
        "app.scraper.registry.get_scraper", lambda s: FakeScraper())
    try:
        with TestClient(app) as client:
            body = client.get("/jobs/search", params={
                "q": "python fase3", "pages": 1,
                "source": "computrabajo", "analyze": False,
            }).json()
            assert body["found"] == 1
            assert body["saved"] == 1
            assert body["jobs"][0]["url"] == "https://example.com/fase3-1"
    finally:
        from app.database.connection import SessionLocal
        from app.database.models import Job

        db = SessionLocal()
        try:
            db.query(Job).filter(
                Job.company == "Empresa F3").delete(
                    synchronize_session=False)
            db.commit()
        finally:
            db.close()
