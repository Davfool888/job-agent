"""Busqueda progresiva SSE: eventos por pagina, guardado sin duplicar."""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


class FakeScraper:
    source = "computrabajo"

    def __init__(self, pages=3, fail_at=None):
        self._pages = pages
        self._fail_at = fail_at

    def search(self, query, max_pages=1, include_details=False,
               location=None, on_page=None):
        total = []
        for page in range(1, min(max_pages, self._pages) + 1):
            if self._fail_at == page:
                raise RuntimeError("fuente caida en pagina 2")
            batch = [{
                "title": f"Cargo Stream {query} p{page} i{i}",
                "company": "Empresa Stream",
                "url": f"https://example.com/stream-{page}-{i}",
                "description": f"Oferta de {query} numero {page}-{i} "
                "con Python y SQL para datos",
                "source": "computrabajo",
            } for i in range(3)]
            total.extend(batch)
            if on_page is not None:
                on_page(list(batch), page)
        return total


def _fake(monkeypatch, **kwargs):
    import app.main as main_module

    monkeypatch.setattr(
        main_module, "get_scraper", lambda source: FakeScraper(**kwargs))


def _read_sse(client, params):
    with client.stream("GET", "/jobs/search/stream",
                       params=params) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/event-stream")
        events = []
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                raw, buffer = buffer.split("\n\n", 1)
                for line in raw.splitlines():
                    if line.startswith("data:"):
                        events.append(json.loads(line[5:].strip()))
        return events


def _clean():
    from app.database.connection import SessionLocal
    from app.database.models import Job

    db = SessionLocal()
    try:
        db.query(Job).filter(
            Job.company == "Empresa Stream").delete(
                synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_stream_emits_jobs_progressively(monkeypatch):
    _fake(monkeypatch, pages=3)
    _clean()
    try:
        with TestClient(app) as client:
            events = _read_sse(client, {
                "q": "python stream", "pages": 3,
                "source": "computrabajo", "analyze": False,
            })
        kinds = [e["type"] for e in events]
        assert kinds[0] == "started"
        jobs_events = [e for e in events if e["type"] == "jobs"]
        # Una emision por pagina scrapeada (progresivo, no todo al final).
        assert [e["page"] for e in jobs_events] == [1, 2, 3]
        assert sum(len(e["jobs"]) for e in jobs_events) == 9
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        assert done[0]["found"] == 9
        assert done[0]["saved_unique"] == 9
        # Todo quedo guardado con links.
        from app.database.connection import SessionLocal
        from app.services.job_service import get_job_by_url

        db = SessionLocal()
        try:
            assert get_job_by_url(
                db, "https://example.com/stream-2-1") is not None
        finally:
            db.close()
    finally:
        _clean()


def test_stream_no_duplicates_on_rerun(monkeypatch):
    _fake(monkeypatch, pages=2)
    _clean()
    try:
        with TestClient(app) as client:
            first = [e for e in _read_sse(client, {
                "q": "python stream", "pages": 2,
                "source": "computrabajo", "analyze": False,
            }) if e["type"] == "done"][0]
            second = [e for e in _read_sse(client, {
                "q": "python stream", "pages": 2,
                "source": "computrabajo", "analyze": False,
            }) if e["type"] == "done"][0]
        assert first["saved_unique"] == 6
        # Segunda vez: mismas URLs -> mismos ids, sin filas nuevas.
        assert second["saved_unique"] == 6
        from app.database.connection import SessionLocal
        from app.database.models import Job

        db = SessionLocal()
        try:
            assert db.query(Job).filter(
                Job.company == "Empresa Stream").count() == 6
        finally:
            db.close()
    finally:
        _clean()


def test_stream_error_event_on_source_failure(monkeypatch):
    _fake(monkeypatch, pages=3, fail_at=2)
    _clean()
    try:
        with TestClient(app) as client:
            events = _read_sse(client, {
                "q": "python stream", "pages": 3,
                "source": "computrabajo", "analyze": False,
            })
        kinds = [e["type"] for e in events]
        assert "jobs" in kinds  # la pagina 1 si llego
        errors = [e for e in events if e["type"] == "error"]
        assert len(errors) == 1
        assert "pagina 2" in errors[0]["message"]
        assert not [e for e in events if e["type"] == "done"]
    finally:
        _clean()


def test_stream_validates_query():
    with TestClient(app) as client:
        response = client.get("/jobs/search/stream",
                              params={"q": "x", "pages": 1})
        assert response.status_code == 422


def test_all_scrapers_accept_on_page():
    """Contrato: los 5 scrapers aceptan el hook progresivo."""
    import inspect

    from app.scraper import computrabajo, elempleo, indeed, linkedin, magneto

    modules = [computrabajo, elempleo, indeed, linkedin, magneto]
    assert len(modules) == 5
    for module in modules:
        scraper_cls = next(
            obj for name, obj in vars(module).items()
            if name.endswith("Scraper") and name != "BaseScraper"
        )
        params = inspect.signature(scraper_cls.search).parameters
        assert "on_page" in params, module.__name__
