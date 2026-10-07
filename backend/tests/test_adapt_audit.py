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


def test_verify_rechaza_tecnologia_y_metrica_nueva():
    from app.adapt import rewrite as rewrite_module

    originals = ["Analicé datos con Python para reportes.",
                 "Automaticé 30 reportes mensuales con Excel."]
    ok, _ = rewrite_module.verify_rewrite(
        originals, ["Analicé datos con Python y Go para reportes.",
                    "Automaticé 30 reportes mensuales con Excel."])
    assert ok is False
    ok, _ = rewrite_module.verify_rewrite(
        originals, ["Analicé datos con Python para reportes.",
                    "Automaticé 500 reportes mensuales con Excel."])
    assert ok is False
    ok, _ = rewrite_module.verify_rewrite(
        originals, ["Analicé datos con Python para reportes.",
                    "Automaticé 30 reportes mensuales con Excel."])
    assert ok is True


def test_rewrite_apagado_conserva_original():
    from app.adapt import rewrite as rewrite_module

    originals = ["Hice cosas con Python."]
    out = rewrite_module.rewrite_bullets(originals, ["Python"], "Dev")
    assert out["bullets"] == originals
    assert out["provider"] == "none"


def test_rewrite_acepta_limpio_y_rechaza_sucio(monkeypatch):
    from app.adapt import rewrite as rewrite_module

    monkeypatch.setattr(rewrite_module, "rewrite_available", lambda: True)
    import json as _json

    seen = {}

    class _FakeProvider:
        def available(self):
            return True

        def _generate(self, prompt, timeout):
            return _json.dumps({"bullets": seen["out"]})

    monkeypatch.setattr("app.adapt.rewrite.GeminiProvider",
                        _FakeProvider, raising=False)
    # GeminiProvider se importa dentro de la funcion; se parcha el modulo.
    import app.ai.providers.gemini as gemini_module

    monkeypatch.setattr(gemini_module.GeminiProvider, "available",
                        lambda self: True)
    monkeypatch.setattr(gemini_module.GeminiProvider, "_generate",
                        _FakeProvider()._generate)
    originals = ["Analicé datos con Python."]
    seen["out"] = ["Con Python, analicé datos."]
    out = rewrite_module.rewrite_bullets(originals, ["Python"], "Dev")
    assert out["verified"] is True
    assert out["bullets"] == seen["out"]
    seen["out"] = ["Analicé datos con Rust."]
    out = rewrite_module.rewrite_bullets(originals, ["Python"], "Dev")
    assert out["bullets"] == originals
    assert out["verified"] is False


def test_servicio_sin_optin_no_reescribe(tmp_path, monkeypatch):
    import json as _json
    from types import SimpleNamespace

    from app.adapt import service as adapt_service

    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.job_service.get_job_by_id",
        lambda db, job_id: SimpleNamespace(
            id="10", title="Dev", company="Acme",
            description="Python", location="", modality="",
            requirements=[], responsibilities=[]),
    )
    monkeypatch.setattr(
        "app.adapt.guest.get_profile_for_cv",
        lambda *a, **k: {"full_name": "Ana", "summary": "Dev.",
                         "skills_technical": ["Python"],
                         "experiences": [{
                             "title": "Dev", "company": "Acme",
                             "description": "Hice A. Hice B con Python."}]})
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
            db, "10", uid="u10", email="u@x.co")
    finally:
        from app.database.models import PDFConfig

        db.query(PDFConfig).filter(PDFConfig.uid == "u10").delete(
            synchronize_session=False)
        db.commit()
        db.close()
    assert out["success"] is True
    stored = _json.loads((tmp_path / "job_10" / "u10" / "adapt.json")
                         .read_text(encoding="utf-8"))
    assert stored["content"].get("adaptations") == []


def _offer_data():
    return {
        "title": "Analista de Datos",
        "company": "Banco",
        "description": "Buscamos analista de datos con Power BI y SQL "
                       "para reportes. Mínimo 2 años de experiencia.",
        "requirements": ["Power BI", "SQL"],
        "location": "Bogotá",
    }


def test_vacancy_niveles_y_sector():
    from app.adapt.vacancy import analyze_vacancy

    vacancy = analyze_vacancy(_offer_data())
    assert vacancy["role"] == "Analista de Datos"
    assert "Power BI" in vacancy["keywords_high"]
    assert vacancy["sector"] == "financiero"
    assert set(vacancy["requirements"]) == {"Power BI", "SQL"}


def test_compose_title_solo_con_evidencia():
    from app.adapt.selector import compose_title

    vacancy = {"role": "Analista de Datos"}
    assert compose_title("Ingeniero de Software", vacancy,
                         ["Power BI"]) == \
        "Ingeniero de Software | Analista de Datos"
    # Sin evidencia: conserva el del perfil.
    assert compose_title("Ingeniero de Software", vacancy, []) == \
        "Ingeniero de Software"
    # Rol ya contenido: no duplica.
    assert compose_title("Analista de Datos Senior", vacancy,
                         ["SQL"]) == "Analista de Datos Senior"
    # Sin rol: conserva base.
    assert compose_title("Ingeniero", {}, ["SQL"]) == "Ingeniero"


def test_summary_y_bullets_reordenan_sin_recortar():
    from app.adapt.selector import order_bullets, order_summary

    summary = ("Vivo en Bogotá. Domino Python y SQL para análisis. "
               "Me gusta el café.")
    ordered = order_summary(summary, {"python", "sql"})
    assert ordered.index("Domino Python") < ordered.index("Vivo en Bogotá")
    assert "café" in ordered  # nada se elimina

    bullets = order_bullets(
        "General. Consulté clientes a diario. Automaticé reportes con "
        "Python y SQL.", {"python", "sql"})
    assert bullets[0].startswith("Automaticé")
    assert len(bullets) == 2


def test_proyectos_secundarios_recortados_y_skills_priorizadas():
    from app.adapt import selector

    profile = {"skills_technical": ["Excel", "Power BI", "SQL", "Python"],
               "target_roles": [], "title": "Ingeniero de Software"}
    offer = _offer_data()
    from app.adapt import matcher

    matching = matcher.match_offer_profile(offer, profile)
    content = selector.select_cv_content(profile, offer, matching, {})
    # Skills exigidas primero (orden de la oferta).
    assert content["skills"][0] == "Power BI"
    assert "Python" in content["skills"]  # real no exigida: sigue al final
    # Titulo compuesto con evidencia.
    assert content["title_line"] == \
        "Ingeniero de Software | Analista de Datos"


def test_audit_checklist_titulo_e_intro():
    from app.adapt import audit as audit_module

    profile = {"full_name": "Ana", "skills_technical": ["Power BI"]}
    content = {"title": "Ingeniero de Software | Analista de Datos",
               "summary": "Analista de Datos con Power BI para reportes.",
               "skills": ["Power BI"],
               "experiences": [], "education": [], "projects": [],
               "certifications": []}
    report = audit_module.audit_cv(
        content, profile, _offer_data(), {}, None)
    assert any("Titulo alineado" in a
               for a in report["improvements_allowed"])
    assert any("menciona el rol" in a
               for a in report["improvements_allowed"])


def test_ia_una_sola_via_con_cliente_usuario(tmp_path, monkeypatch):
    """Con keys del usuario, el pulido global NO se ejecuta."""
    import json as _json
    from types import SimpleNamespace

    from app.adapt import llm as adapt_llm
    from app.adapt import service as adapt_service
    from app.ai import user_llm

    calls = {"global": 0}

    def _fake_global(*args, **kwargs):
        calls["global"] += 1
        return {"summary": "global", "provider": "gemini"}

    class _FakeClient:
        provider_used = "deepseek"

    def _fake_for_user(db, uid, preferred=None):
        return _FakeClient()

    def _fake_polish(client, original, role, matched):
        assert client.provider_used == "deepseek"
        return {"summary": "pulido-usuario", "provider": "deepseek"}

    monkeypatch.setattr(adapt_llm, "polish_summary", _fake_global)
    monkeypatch.setattr(user_llm, "for_user", _fake_for_user)
    monkeypatch.setattr(user_llm, "polish_summary_for_user", _fake_polish)
    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.job_service.get_job_by_id",
        lambda db, job_id: SimpleNamespace(
            id="11", title="Dev", company="Acme",
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
            db, "11", uid="u11", email="u@x.co")
    finally:
        from app.database.models import PDFConfig

        db.query(PDFConfig).filter(PDFConfig.uid == "u11").delete(
            synchronize_session=False)
        db.commit()
        db.close()
    assert out["success"] is True
    assert calls["global"] == 0
    stored = _json.loads((tmp_path / "job_11" / "u11" / "adapt.json")
                         .read_text(encoding="utf-8"))
    assert stored["content"]["summary"] == "pulido-usuario"
    assert stored["content"]["summary_provider"] == "deepseek"


def test_blocking_issues_solo_veracidad_y_config():
    from app.adapt.audit import blocking_issues

    audit = {"issues": [
        {"area": "veracidad", "message": "x", "blocking": True},
        {"area": "configuracion", "message": "y", "blocking": True},
        {"area": "estructura", "message": "z", "blocking": False},
        {"area": "ats", "message": "w", "blocking": True},
    ]}
    blocked = blocking_issues(audit)
    assert len(blocked) == 2
    assert blocking_issues({"issues": []}) == []
    assert blocking_issues({}) == []


def test_servicio_no_entrega_con_bloqueantes(tmp_path, monkeypatch):
    """Audit con bloqueantes -> AUDIT_FAILED, no success."""
    import json as _json
    from types import SimpleNamespace

    from app.adapt import service as adapt_service

    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.job_service.get_job_by_id",
        lambda db, job_id: SimpleNamespace(
            id="12", title="Dev", company="Acme",
            description="Python", location="", modality="",
            requirements=[], responsibilities=[]),
    )
    monkeypatch.setattr(
        "app.adapt.guest.get_profile_for_cv",
        lambda *a, **k: {"full_name": "Ana", "summary": "Dev.",
                         "skills_technical": ["Python"],
                         "experiences": []})
    monkeypatch.setattr(
        "app.adapt.service._is_profile_complete", lambda raw: True)

    def _fake_render(html_text, out, timeout):
        __import__("pathlib").Path(out).write_bytes(b"%PDF-1.4 fake")
        return out

    monkeypatch.setattr("app.adapt.pdf._render_locked", _fake_render)

    def _fake_audit(content, profile, offer, config, pdf_path):
        return {"passed": False,
                "scores": {"veracidad": 40},
                "issues": [{"area": "veracidad", "message": "invento",
                            "blocking": True}],
                "improvements_allowed": [],
                "improvements_blocked": [],
                "facts": {"pages": 1, "chars": 500, "readable": True},
                "keyword_coverage": {}}

    monkeypatch.setattr("app.adapt.audit.audit_cv", _fake_audit)
    from app.database.connection import SessionLocal

    db = SessionLocal()
    try:
        with __import__("pytest").raises(adapt_service.AdaptError) as exc:
            adapt_service.adapt_profile_for_job(
                db, "12", uid="u12", email="u@x.co")
    finally:
        from app.database.models import PDFConfig

        db.query(PDFConfig).filter(PDFConfig.uid == "u12").delete(
            synchronize_session=False)
        db.commit()
        db.close()
    assert exc.value.code == "AUDIT_FAILED"


def test_timings_en_respuesta_y_json(tmp_path, monkeypatch):
    import json as _json
    from types import SimpleNamespace

    from app.adapt import service as adapt_service

    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    monkeypatch.setattr(
        "app.services.job_service.get_job_by_id",
        lambda db, job_id: SimpleNamespace(
            id="13", title="Dev", company="Acme",
            description="Python", location="", modality="",
            requirements=[], responsibilities=[]),
    )
    monkeypatch.setattr(
        "app.adapt.guest.get_profile_for_cv",
        lambda *a, **k: {"full_name": "Ana", "summary": "Dev.",
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
            db, "13", uid="u13", email="u@x.co")
    finally:
        from app.database.models import PDFConfig

        db.query(PDFConfig).filter(PDFConfig.uid == "u13").delete(
            synchronize_session=False)
        db.commit()
        db.close()
    assert out["success"] is True
    for stage in ("config", "job", "profile", "coerce", "match",
                  "select", "llm", "validate", "render", "pdf",
                  "audit", "finish"):
        assert stage in out["timings"], stage
        assert isinstance(out["timings"][stage], (int, float))
    stored = _json.loads((tmp_path / "job_13" / "u13" / "adapt.json")
                         .read_text(encoding="utf-8"))
    assert stored["timings"] == out["timings"]


def test_download_409_con_auditoria_bloqueante(tmp_path, monkeypatch):
    import json as _json

    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    from app.database.connection import SessionLocal
    from app.services.job_service import save_jobs

    db = SessionLocal()
    try:
        saved = save_jobs(db, [{
            "title": "Dev Bloqueado", "company": "Empresa Auditoria 409",
            "url": "https://example.com/auditoria-409",
            "description": "Python " * 20, "source": "computrabajo"}],
            search_query="auditoria")
        job_id = saved[0].id
        target = tmp_path / f"job_{job_id}" / "guest"
        target.mkdir(parents=True, exist_ok=True)
        (target / "cv.pdf").write_bytes(b"%PDF-1.4 fake")
        (target / "adapt.json").write_text(_json.dumps({
            "audit": {"passed": False, "issues": [
                {"area": "veracidad", "message": "invento",
                 "blocking": True}]}}), encoding="utf-8")
        with TestClient(app) as client:
            response = client.get(
                f"/jobs/{job_id}/adapt-cv/download",
                params={"format": "pdf"})
            assert response.status_code == 409, response.status_code
    finally:
        from app.database.models import Job

        db.query(Job).filter(
            Job.company == "Empresa Auditoria 409").delete(
                synchronize_session=False)
        db.commit()
        db.close()

