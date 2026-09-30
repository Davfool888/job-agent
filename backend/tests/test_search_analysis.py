"""Problema 2: /jobs/search analiza despues del scraping.

Usa un scraper falso (sin red): una oferta de datos con titulo generico
y una oferta irrelevante que solo menciona Excel.
"""
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app

AUX_INFO_DESC = (
    "Creación de dashboards en Power BI, transformación de datos con "
    "Power Query, análisis de indicadores y manejo de SQL. Requisitos: "
    "Excel avanzado, 2 años de experiencia en análisis de información."
)
BODEGA_DESC = (
    "Se solicita auxiliar de bodega para cargue y descargue. "
    "Requisito: manejo de Excel para planillas básicas."
)


class FakeScraper:
    source = "falsa"

    def search(self, query, max_pages=1, include_details=False):
        return [
            {
                "title": "Auxiliar de información",
                "company": "Empresa Datos XYZ",
                "location": "Bogotá",
                "url": "https://example.com/oferta-datos-xyz",
                "description": AUX_INFO_DESC,
                "source": "falsa",
            },
            {
                "title": "Auxiliar de bodega",
                "company": "Empresa Bodega XYZ",
                "location": "Bogotá",
                "url": "https://example.com/oferta-bodega-xyz",
                "description": BODEGA_DESC,
                "source": "falsa",
            },
        ]

    def get_job_detail(self, url):
        raise AssertionError("no deberia pedir detalles: ya hay descripcion")


@pytest.fixture()
def fake_source(monkeypatch):
    monkeypatch.setattr(main_module, "get_scraper", lambda source: FakeScraper())
    from app.database.connection import SessionLocal
    from app.database.models import Job, Profile

    db = SessionLocal()
    previous_profile = db.query(Profile).filter(Profile.id == 1).first()
    previous_data = previous_profile.data if previous_profile else None
    db.close()
    yield
    db = SessionLocal()
    try:
        db.query(Job).filter(
            Job.url.in_(
                [
                    "https://example.com/oferta-datos-xyz",
                    "https://example.com/oferta-bodega-xyz",
                ]
            )
        ).delete(synchronize_session=False)
        if previous_data is not None:
            row = db.query(Profile).filter(Profile.id == 1).first()
            if row:
                row.data = previous_data
                db.add(row)
        db.commit()
    finally:
        db.close()


def test_search_analiza_y_persiste(fake_source):
    with TestClient(app) as client:
        client.put(
            "/profile",
            json={
                "skills": ["Python", "SQL", "Power BI", "Excel"],
                "target_roles": ["Data Analyst"],
            },
        )
        response = client.get(
            "/jobs/search",
            params={"q": "analista de datos", "source": "cualquiera"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["found"] == 2
        assert body["analyzed"] == 2
        assert body["relevant"] >= 1

        by_url = {j["url"]: j for j in body["jobs"]}
        datos = by_url["https://example.com/oferta-datos-xyz"]
        bodega = by_url["https://example.com/oferta-bodega-xyz"]

        # Titulo generico, rol detectado por contenido (DATA_ANALYST o
        # BI_ANALYST: ambos son relevantes para busquedas de datos).
        assert datos["match_score"] is not None and datos["match_score"] >= 50
        assert datos["category"] in ("DATA_ANALYST", "BI_ANALYST")
        assert datos["detected_role"] is not None

        # Solo menciona Excel -> OTHER y score bajo.
        assert bodega["category"] == "OTHER"
        assert bodega["match_score"] < 25

        # Persistido: published_title intacto, detected_role separado.
        stored = client.get(f"/jobs/{datos['id']}").json()
        assert stored["title"] == "Auxiliar de información"
        assert stored["detected_role"] is not None
        assert stored["category"] in ("DATA_ANALYST", "BI_ANALYST")
        assert "Power BI" in stored["evidence"] or "power bi" in " ".join(
            stored["evidence"]
        ).lower()
        assert stored["matched_skills"] != []
        assert stored["missing_skills"] != []


def test_search_sin_analisis_es_solo_guardado(fake_source):
    with TestClient(app) as client:
        response = client.get(
            "/jobs/search",
            params={"q": "analista de datos", "analyze": "false"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["analyzed"] == 0
        for job in body["jobs"]:
            assert job["match_score"] is None
            assert job["detected_role"] is None
