"""Configuracion de PDF: validaciones, APA fijo y orden real."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _ensure_tables():
    from app.database.connection import Base, engine

    Base.metadata.create_all(bind=engine)


@pytest.fixture()
def _auth(monkeypatch):
    import app.auth as auth_module

    def fake_verify(authorization):
        assert (authorization or "").startswith("Bearer ")
        return {"uid": "uid-pdf-test", "email": "pdf@test.test",
                "name": "PDF"}

    monkeypatch.setattr(auth_module, "verify_bearer_token", fake_verify)
    yield
    from app.database.connection import SessionLocal
    from app.database.models import PDFConfig

    db = SessionLocal()
    try:
        db.query(PDFConfig).filter(
            PDFConfig.uid == "uid-pdf-test").delete(
                synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _headers():
    return {"Authorization": "Bearer x"}


def test_font_size_only_allows_menu(_auth):
    with TestClient(app) as client:
        bad = client.put("/pdf-config", json={"font_size_pt": 13},
                         headers=_headers())
        assert bad.status_code == 400
        ok = client.put("/pdf-config", json={"font_size_pt": 14},
                        headers=_headers())
        assert ok.status_code == 200
        assert ok.json()["font_size_pt"] == 14


def test_margins_apa_and_black_always(_auth):
    with TestClient(app) as client:
        body = client.put("/pdf-config", json={
            "margin_top_mm": 10, "margin_left_mm": 40,
            "accent_color": "#ff0000",
        }, headers=_headers()).json()
        assert body["margin_top_mm"] == 25
        assert body["margin_bottom_mm"] == 25
        assert body["margin_left_mm"] == 25
        assert body["margin_right_mm"] == 25
        assert body["accent_color"] == "#000000"
        reset = client.post("/pdf-config/reset",
                            headers=_headers()).json()
        assert reset["margin_top_mm"] == 25
        assert reset["accent_color"] == "#000000"


def test_section_order_changes_document_order(_auth):
    from app.adapt import html_renderer

    content = {
        "full_name": "Prueba Orden",
        "target_role": "Analista",
        "summary": "Resumen.",
        "skills": ["Python"],
        "experiences": [{
            "title": "Cargo X", "company": "Empresa X",
            "description": "Hizo cosas. Muchas cosas.",
        }],
        "education": [], "projects": [], "certifications": [],
        "languages": [],
    }
    normal = html_renderer.render_cv_html(
        content, None, {"section_order": ["summary", "experience"]})
    swapped = html_renderer.render_cv_html(
        content, None, {"section_order": ["experience", "summary"]})
    assert normal.index("Perfil Profesional") < normal.index(
        "Experiencia Profesional")
    assert swapped.index("Experiencia Profesional") < swapped.index(
        "Perfil Profesional")


def test_date_format_applies():
    from app.adapt import html_renderer

    content = {
        "full_name": "Prueba Fecha",
        "experiences": [{
            "title": "Cargo", "company": "Empresa",
            "start_date": "2026-03-01", "end_date": "2026-08-01",
            "description": "Hizo cosas.",
        }],
        "education": [], "projects": [], "certifications": [],
        "languages": [], "skills": [],
    }
    iso = html_renderer.render_cv_html(content, None, {"date_format": "MM/YYYY"})
    assert "03/2026" in iso
    long = html_renderer.render_cv_html(
        content, None, {"date_format": "MMMM YYYY"})
    assert "Marzo 2026" in long
    default = html_renderer.render_cv_html(content, None, {})
    assert "Mar 2026" in default
