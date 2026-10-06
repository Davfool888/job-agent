"""Auditoria config-driven del CV adaptado.

- La config manda sobre la relevancia (topes).
- El renderer respeta visibilidad/longitud/bullets.
- La auditoria detecta invencion, violaciones de config y paginas.
"""
import re as _re


def _matching_three_projects():
    return {
        "percentage": 90,
        "matched_skills": ["Python"],
        "missing_skills": [],
        "experiences": [],
        "projects": [
            {"score": 3, "item": {"name": "P1", "description": "d1"}},
            {"score": 2, "item": {"name": "P2", "description": "d2"}},
            {"score": 1, "item": {"name": "P3", "description": "d3"}},
        ],
        "certifications": [],
        "education": [],
    }


def test_selector_config_manda_sobre_relevancia():
    from app.adapt import selector

    profile = {"skills_technical": ["Python"], "target_roles": []}
    offer = {"title": "Dev", "company": "", "description": ""}
    out = selector.select_cv_content(
        profile, offer, _matching_three_projects(),
        {"max_projects": 2})
    assert [p["name"] for p in out["projects"]] == ["P1", "P2"]
    out = selector.select_cv_content(
        profile, offer, _matching_three_projects(), {})
    assert len(out["projects"]) == 3


def test_renderer_respeta_visibilidad_y_topes():
    from app.adapt import html_renderer as html

    content = {
        "full_name": "T",
        "summary": ("Primera oracion larga sobre el perfil profesional "
                    "del candidato con detalle suficiente. Segunda oracion "
                    "con mas detalle tecnico relevante para la oferta. "
                    "Tercera oracion de relleno para superar el tope corto "
                    "con creces y forzar el recorte por presupuesto. Cuarta "
                    "oracion adicional que tambien debe quedar fuera del "
                    "resumen corto porque excede el presupuesto de "
                    "caracteres permitido por la configuracion. Quinta "
                    "oracion extra de relleno para asegurar el recorte."),
        "experiences": [{
            "title": "Dev", "company": "Acme",
            "description": "Uno. Dos. Tres. Cuatro.",
        }],
        "skills_soft": ["Liderazgo"],
        "languages": [{"label": "Inglés", "level": "B1"}],
        "linkedin": "https://linkedin.com/in/x",
    }
    hidden = html.render_cv_html(content, None, {
        "font_size_pt": 11, "show_soft_skills": False,
        "show_languages": False, "show_links": False,
        "profile_length": "short", "max_bullets": 1,
        "section_order": ["summary", "experience", "soft_skills",
                          "languages"],
    })
    assert "Liderazgo" not in hidden
    assert "linkedin.com" not in hidden
    assert "Cuatro" not in hidden  # 1 bullet: solo primera oracion
    assert "Quinta" not in hidden  # short recorta por oraciones
    assert "Primera oracion" in hidden

    shown = html.render_cv_html(content, None, {"font_size_pt": 11})
    assert "Liderazgo" in shown and "Cuatro" in shown


def test_audit_detecta_invencion():
    from app.adapt import audit as audit_module

    profile = {"full_name": "Ana", "skills_technical": ["Python"],
               "experiences": []}
    content = {"summary": "Dev.",
               "skills": ["Python", "CobolMainframeX"],
               "experiences": [], "education": [], "projects": [],
               "certifications": []}
    report = audit_module.audit_cv(content, profile, {}, {}, None)
    assert report["passed"] is False
    assert any(i["area"] == "veracidad" and i["blocking"]
               for i in report["issues"])
    assert report["scores"]["veracidad"] == 40


def test_audit_pasa_contenido_limpio():
    from app.adapt import audit as audit_module

    profile = {"full_name": "Ana", "skills_technical": ["Python"],
               "experiences": []}
    content = {"summary": "Dev Python.",
               "skills": ["Python"],
               "skills_groups": {"programming": ["Python"]},
               "experiences": [], "education": [], "projects": [],
               "certifications": []}
    report = audit_module.audit_cv(content, profile, {}, {}, None)
    assert report["passed"] is True
    assert report["scores"]["veracidad"] == 100
    assert report["scores"]["configuracion"] == 100


def test_audit_tope_proyectos_bloquea():
    from app.adapt import audit as audit_module

    profile = {"skills_technical": ["Python"]}
    content = {"projects": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
               "experiences": [], "education": [], "certifications": []}
    report = audit_module.audit_cv(
        content, profile, {}, {"max_projects": 2}, None)
    assert report["passed"] is False
    assert any("maximo configurado (2)" in i["message"]
               for i in report["issues"])


def test_audit_paginas_con_pdf_real(tmp_path):
    from app.adapt import audit as audit_module

    content = {"summary": "Dev.", "experiences": [], "education": [],
               "projects": [], "certifications": []}
    profile = {"full_name": "Ana Torres"}
    # PDF de 3 paginas construido a mano (texto con el nombre).
    pdf_bytes = _pdf_3_pages("Ana Torres")
    target = tmp_path / "cv.pdf"
    target.write_bytes(pdf_bytes)
    report = audit_module.audit_cv(
        content, profile, {}, {"max_pages": 2}, target)
    assert report["facts"]["pages"] == 3
    assert report["passed"] is False
    assert any("maximo (2)" in i["message"] for i in report["issues"])
    ok = audit_module.audit_cv(
        content, profile, {}, {"max_pages": 3}, target)
    assert ok["passed"] is True
    assert ok["facts"]["readable"] is True


def _pdf_3_pages(name: str) -> bytes:
    filler = ("lorem ipsum dolor sit amet " * 12).strip()
    text = (f"BT /F1 12 Tf 72 720 Td 14 TL ({name} CV texto real. "
            f"{filler}) Tj ET")
    content = text.encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 6 0 R /Resources << /Font << /F1 7 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 8\n0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % xref
    return out


def test_servicio_guarda_auditoria(tmp_path, monkeypatch):
    import json as _json
    from types import SimpleNamespace

    from app.adapt import service as adapt_service

    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.job_service.get_job_by_id",
        lambda db, job_id: SimpleNamespace(
            id="9", title="Dev", company="Acme",
            description="Python", location="", modality="",
            requirements=[], responsibilities=[]),
    )
    monkeypatch.setattr(
        "app.adapt.guest.get_profile_for_cv",
        lambda *a, **k: {"full_name": "Ana", "summary": "Dev Python.",
                         "skills_technical": ["Python"],
                         "experiences": []})
    monkeypatch.setattr(
        "app.adapt.service._is_profile_complete", lambda raw: True)

    def _fake_render(html_text, out, timeout):
        __import__("pathlib").Path(out).write_bytes(b"%PDF-1.4 fake")
        return out

    monkeypatch.setattr("app.adapt.pdf._render_locked", _fake_render)
    from app.database.connection import SessionLocal

    db = SessionLocal()
    try:
        out = adapt_service.adapt_profile_for_job(
            db, "9", uid="u9", email="u@x.co")
    finally:
        from app.database.models import PDFConfig

        db.query(PDFConfig).filter(PDFConfig.uid == "u9").delete(
            synchronize_session=False)
        db.commit()
        db.close()
    assert out["success"] is True
    assert "audit" in out and out["audit"]["scores"]["veracidad"] == 100
    stored = _json.loads((tmp_path / "job_9" / "u9" / "adapt.json")
                         .read_text(encoding="utf-8"))
    assert stored["audit"]["passed"] is True

