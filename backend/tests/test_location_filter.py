"""Filtro por ciudad en /jobs/search (sin red)."""
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.scraper.base import (
    filter_by_location,
    matches_location,
    normalize_location_text,
)


def test_normalize_location_text():
    assert normalize_location_text("Bogotá, D.C.") == "bogota, d.c."
    assert normalize_location_text("MEDELLÍN") == "medellin"
    assert normalize_location_text(None) == ""
    assert normalize_location_text("  ") == ""


def test_matches_location():
    # Coincidencia insensible a tildes/mayusculas y por subcadena.
    assert matches_location("Bogotá, D.C.", "bogota") is True
    assert matches_location("Bogotá", "Bogotá") is True
    assert matches_location("Medellín, Antioquia", "medellin") is True
    assert matches_location("Cali, Valle", "bogota") is False
    # Sin filtro o sin ubicacion en la oferta: no se descarta.
    assert matches_location("Cali", None) is True
    assert matches_location("Cali", "  ") is True
    assert matches_location("", "bogota") is True
    assert matches_location(None, "bogota") is True


def test_filter_by_location_keeps_all_without_query():
    jobs = [{"location": "Cali"}, {"location": ""}]
    assert filter_by_location(jobs, None) == jobs
    assert filter_by_location(jobs, "  ") == jobs


def test_filter_by_location_filters():
    jobs = [
        {"title": "a", "location": "Bogotá, D.C."},
        {"title": "b", "location": "Medellín"},
        {"title": "c", "location": ""},
        {"title": "d"},
    ]
    filtered = filter_by_location(jobs, "Bogotá")
    assert [j["title"] for j in filtered] == ["a", "c", "d"]


class FakeScraperWithLocation:
    source = "falsa"

    def search(self, query, max_pages=1, include_details=False, location=None):
        from app.scraper.base import filter_by_location as _filter

        jobs = [
            {
                "title": "Dev Bogotá",
                "company": "C1",
                "location": "Bogotá",
                "url": "https://example.com/loc-bog",
                "description": "Python y SQL en Bogotá.",
                "source": "falsa",
            },
            {
                "title": "Dev Medellín",
                "company": "C2",
                "location": "Medellín, Antioquia",
                "url": "https://example.com/loc-med",
                "description": "Python y SQL en Medellín.",
                "source": "falsa",
            },
        ]
        return _filter(jobs, location)

    def get_job_detail(self, url):
        raise AssertionError("no deberia pedir detalles: ya hay descripcion")


@pytest.fixture()
def fake_source_location(monkeypatch):
    monkeypatch.setattr(
        main_module, "get_scraper", lambda source: FakeScraperWithLocation()
    )
    from app.database.connection import SessionLocal
    from app.database.models import Job

    yield
    db = SessionLocal()
    try:
        db.query(Job).filter(
            Job.url.in_(
                [
                    "https://example.com/loc-bog",
                    "https://example.com/loc-med",
                ]
            )
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_search_endpoint_accepts_location(fake_source_location):
    with TestClient(app) as client:
        response = client.get(
            "/jobs/search",
            params={"q": "desarrollador python", "location": "Bogotá"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["location"] == "Bogotá"
        assert body["found"] == 1
        assert body["jobs"][0]["location"] == "Bogotá"


def test_search_endpoint_without_location_returns_all(fake_source_location):
    with TestClient(app) as client:
        response = client.get("/jobs/search", params={"q": "dev"})
        assert response.status_code == 200, response.text
        assert response.json()["found"] == 2
