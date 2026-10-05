"""Contrato de formatos: Perfil normaliza y Adapt coerciona sin tocar.

- Servicio Perfil (schema): 'diez' -> 10, '03/2025' y '15/07/2026'
  -> ISO. Lo irreconocible -> None + warning, nunca inventado.
- Servicio Adapt (adapt/content.py): recibe el perfil display y
  devuelve COPIAS con los tipos exactos del matcher/renderer mas
  warnings. Lo guardado queda intacto.
"""
from copy import deepcopy


def test_years_palabras():
    from app.profile.schema import _to_years

    assert _to_years("diez") == 10
    assert _to_years("Diez años") == 10
    assert _to_years("dos años y medio") == 2.5
    assert _to_years("three years") == 3
    assert _to_years("1,5") == 1.5
    assert _to_years(4) == 4
    assert _to_years("") is None
    assert _to_years(None) is None
    assert _to_years("muchos años") is None
    assert _to_years("70") is None
    assert _to_years("hola mundo como estas") is None


def test_normalize_date_formatos_display():
    from app.profile.schema import normalize_date

    assert normalize_date("03/2025") == "2025-03-01"
    assert normalize_date("15/07/2026") == "2026-07-15"
    assert normalize_date("2026-03-01") == "2026-03-01"
    assert normalize_date("Mar 2025") == "2025-03-01"
    assert normalize_date("marzo 2026") == "2026-03-01"
    assert normalize_date("2026") == "2026-01-01"
    assert normalize_date("13/2025") is None
    assert normalize_date("32/01/2026") is None
    assert normalize_date("ayer") is None


def test_coerce_profile_tipos_y_sin_mutar():
    from app.adapt import content as adapt_content

    messy = {
        "full_name": "  Ana Torres ",
        "title": None,
        "email": "a@b.co",
        "phone": 123,
        "years_experience": "diez",
        "skills_technical": ["Python", "", None, "Python"],
        "skills_soft": "liderazgo",
        "skills_groups": {"data": ["SQL", 5]},
        "target_roles": None,
        "languages": [{"label": "Inglés", "level": "B1"}],
        "experiences": [{
            "title": "Dev", "company": "Acme",
            "start": "Mar 2025", "technical_skills": "Python",
        }],
        "education": "no-lista",
        "projects": [],
        "other_knowledge": "REST, APIs",
    }
    snapshot = deepcopy(messy)
    out, warnings = adapt_content.coerce_profile(messy)
    assert messy == snapshot  # no muta la entrada
    assert out["full_name"] == "Ana Torres"
    assert out["title"] == ""
    assert out["phone"] == "123"
    assert out["years_experience"] == 10
    assert out["skills_technical"] == ["Python"]
    assert out["skills_soft"] == ["liderazgo"]
    assert out["skills_groups"] == {"data": ["SQL"]}
    assert out["target_roles"] == []
    lang = out["languages"][0]
    assert (lang["level"], lang["listening"], lang["speaking"]) == (
        "B1", "B1", "B1")
    exp = out["experiences"][0]
    assert exp["start"] == "Mar 2025"
    assert exp["technical_skills"] == ["Python"]
    assert any("education" in w for w in warnings)


def test_coerce_profile_years_irreconocible():
    from app.adapt import content as adapt_content

    out, warnings = adapt_content.coerce_profile(
        {"years_experience": "muchísimo tiempo"})
    assert out["years_experience"] is None
    assert any("years_experience" in w for w in warnings)


def test_coerce_pdf_config_tipos():
    from app.adapt import content as adapt_content

    cfg, warnings = adapt_content.coerce_pdf_config({
        "font_family": "Comic Sans",
        "font_size_pt": "13",
        "section_order": '["experience", "narnia", "skills"]',
        "date_format": "ayer",
        "margin_top_mm": "25",
        "section_spacing_pt": None,
    })
    assert cfg["font_family"] == "georgia"
    assert cfg["font_size_pt"] == 11
    assert cfg["section_order"] == ["experience", "skills"]
    assert cfg["date_format"] == "MMM YYYY"
    assert cfg["margin_top_mm"] == 25
    assert cfg["section_spacing_pt"] == 14
    assert len(warnings) >= 4

    cfg2, warnings2 = adapt_content.coerce_pdf_config({
        "font_size_pt": 14, "section_order": ["skills", "experience"],
        "date_format": "MM/YYYY",
    })
    assert warnings2 == []
    assert cfg2["font_size_pt"] == 14
    assert cfg2["section_order"] == ["skills", "experience"]


def test_adapt_cableado_coercion_sin_chromium(tmp_path, monkeypatch):
    """Perfil display sucio -> adapt_profile_for_job coerciona, renderiza
    HTML y reporta warnings, sin tocar lo guardado (PDF simulado)."""
    import json as _json
    from types import SimpleNamespace

    from app.adapt import service as adapt_service

    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.job_service.get_job_by_id",
        lambda db, job_id: SimpleNamespace(
            id="7", title="Analista de Datos", company="Banco",
            description="Python SQL Power BI", location="Bogotá",
            modality="", requirements=[], responsibilities=[]),
    )
    messy = {
        "full_name": "Ana Torres", "title": "Analista",
        "email": "a@b.co", "phone": None,
        "years_experience": "diez",
        "skills_technical": ["Python", 5, ""],
        "skills_soft": [],
        "skills_groups": {},
        "summary": "Resumen.",
        "languages": [{"label": "Inglés", "level": "B1"}],
        "experiences": [{
            "title": "Analista", "company": "Acme",
            "start": "Mar 2025", "end": "Dic 2025",
            "description": "Analicé datos con Python.",
            "technical_skills": ["Python"],
        }],
        "education": [], "projects": [], "certifications": [],
    }
    monkeypatch.setattr(
        "app.adapt.guest.get_profile_for_cv", lambda *a, **k: dict(messy))
    # El chequeo de completitud lee el perfil real: se simula completo
    # (lo que se prueba aqui es la coercion, no el gate).
    monkeypatch.setattr(
        "app.adapt.service._is_profile_complete", lambda raw: True)
    monkeypatch.setattr(
        "app.adapt.pdf.html_to_pdf",
        lambda html, out, *a, **k: __import__("pathlib").Path(out).write_bytes(
            b"%PDF-1.4 fake"))

    out = None
    from app.database.connection import SessionLocal

    db = SessionLocal()
    try:
        out = adapt_service.adapt_profile_for_job(
            db, "7", uid="u1", email="u@x.co")
    finally:
        # Limpia la fila PDFConfig auto-creada para u1 en la BD dev.
        from app.database.models import PDFConfig

        db.query(PDFConfig).filter(PDFConfig.uid == "u1").delete(
            synchronize_session=False)
        db.commit()
        db.close()
    assert out["success"] is True
    assert isinstance(out["warnings"], list)
    assert messy["skills_technical"] == ["Python", 5, ""]  # intacto
    stored = _json.loads((tmp_path / "job_7" / "u1" / "adapt.json")
                         .read_text(encoding="utf-8"))
    assert stored["warnings"] == out["warnings"]
    assert stored["matching"]["years_experience"] == 10
    html = (tmp_path / "job_7" / "u1" / "cv.html").read_text(
        encoding="utf-8")
    # Config por defecto MM/YYYY: 'Mar 2025' -> '03/2025' (correcto,
    # no crudo). Lo importante: fechas presentes y formateadas.
    assert "03/2025" in html and "12/2025" in html
