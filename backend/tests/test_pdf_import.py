"""Importador PDF -> perfil: testeado contra CV real (fixture).

Garantias: nada inventado, nada en seccion equivocada, educacion
formal separada de cursos, una descripcion por entrada.
"""
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "sample_cv_pdf.txt"


def _parsed():
    from app.cv import pdf_import as pdf

    text = FIXTURE.read_text(encoding="utf-8")
    return pdf.parse_pdf_profile(text)


def test_personal_completo():
    personal = _parsed()["profile"]["personal"]
    assert personal["full_name"] == "David Santiago Herrera Reales"
    assert personal["first_name"] == "David Santiago"
    assert personal["last_name"] == "Herrera Reales"
    assert personal["email"] == \
        "davidsantiagoherrerareales@gmail.com"
    assert personal["phone"] == "+57 319 565 2138"
    assert personal["location"] == "Bogotá, Colombia"
    assert "linkedin.com/in/david-herrera-reales" in personal["linkedin"]
    assert "github.com/Davfool888" in personal["github"]
    assert "davidherrera-dev.vercel.app" in personal["portfolio"]
    assert "Analista de Datos" in personal["title"]


def test_resumen_no_vacio_y_sin_skills():
    summary = _parsed()["profile"]["professional_summary"]
    assert "Ingeniero de Software" in summary
    assert "10.000 registros" in summary
    assert len(summary) > 300


def test_experiencia_dos_empleos_bien_ubicados():
    exp = _parsed()["profile"]["experience"]
    assert len(exp) == 2
    primero, segundo = exp
    assert "Nomina" in primero["title"] or "Nómina" in primero["title"]
    assert primero["company"] == "Banco de Bogotá"
    assert primero["start_date"] == "2025-03-01"
    assert primero["end_date"] == "2025-12-01"
    assert "10.000 registros" in primero["description"]
    assert "Google Apps Script" in primero["description"]
    assert segundo["title"] == "Asesor Comercial (Prácticas)"
    assert segundo["company"] == "Banco de Bogotá"
    assert segundo["start_date"] == "2023-10-01"
    assert segundo["end_date"] == "2024-10-01"
    assert "Verifiqué" in segundo["description"] or \
        "Verifique" in segundo["description"]
    # Nada de proyectos/educacion colado en experiencia.
    for entry in exp:
        assert "USD/COP" not in entry["description"]
        assert "Politecnico" not in entry["description"]


def test_educacion_formal_con_nivel():
    edu = _parsed()["profile"]["education"]
    assert len(edu) == 2
    niveles = {e["level"] for e in edu}
    assert "bachelor" in niveles  # Ingenieria de Software
    assert "technical" in niveles  # Tecnico SENA
    ing = next(e for e in edu if e["level"] == "bachelor")
    assert ing["degree"] == "Ingeniería de Software"
    assert "Grancolombiano" in ing["institution"]
    assert ing["start_date"] == "2022-04-01"
    assert ing["status"] == "in_progress"  # termina Sep 2026
    tec = next(e for e in edu if e["level"] == "technical")
    assert "SENA" in tec["institution"]
    assert tec["status"] == "finished"
    # Ningun curso colado en educacion formal.
    for entry in edu:
        assert "Platzi" not in entry["degree"]
        assert "DAX" not in entry["degree"]


def test_cursos_a_certificaciones_idioma_a_idiomas():
    profile = _parsed()["profile"]
    certs = profile["certifications"]
    nombres = [c["name"] for c in certs]
    assert any("DAX" in n for n in nombres)
    assert any("Docker" in n for n in nombres)
    assert any("JavaScript" in n for n in nombres)
    assert len(certs) >= 10
    platzi = [c for c in certs if c["institution"] == "Platzi"]
    assert len(platzi) >= 10
    # Nada de cursos en educacion ni viceversa.
    assert not any("Curso" in e["degree"]
                   for e in profile["education"])
    langs = profile["languages"]
    ingles = [l for l in langs if l["language"] == "en"]
    assert ingles, "Ingles B1 debe extraerse de Otros Estudios"
    assert ingles[0]["level"] == "B1"
    assert ingles[0]["academy"] == "Smart Language Academy"
    # Sin desglose: el nivel general aplica a todas las habilidades.
    for key in ("listening", "reading", "writing", "speaking"):
        assert ingles[0][key] == "B1", key


def test_proyectos_tres_con_tecnologias():
    projects = _parsed()["profile"]["projects"]
    assert len(projects) == 3
    nombres = " | ".join(p["name"] for p in projects)
    assert "USD/COP" in nombres
    assert "Retail Intelligence" in nombres
    assert "YOLOv8" in " ".join(
        t for p in projects for t in p["technologies"])
    for project in projects:
        assert len(project["description"]) > 50


def test_skills_sin_prosa_y_sin_inventos():
    profile = _parsed()["profile"]
    skills = profile["skills"]
    assert "Python" in skills["programming"]
    assert "Power BI" in skills["bi"]
    assert "PostgreSQL" in skills["databases"]
    assert "Docker" in skills["tools"]
    for group_items in skills.values():
        for item in group_items:
            assert len(item) <= 60, f"prosa colada: {item[:60]}"
    assert "Pensamiento analítico" in profile["soft_skills"]
    # `Comunicación y trabajo en equipo` del CV se divide en sus dos
    # canonicas (una etiqueta por skill, sin duplicados).
    assert "Comunicación" in profile["soft_skills"]
    assert "Trabajo en equipo" in profile["soft_skills"]
    assert len(profile["soft_skills"]) == 5
    # Todo skill declarado existe en el CV: literal o por variante
    # canonica (`Data Cleaning` evidencia `Limpieza de datos`; a espacios
    # normalizados: el PDF parte lineas en puntos arbitrarios).
    import re as _re

    from app.analysis.skills_canonical import canonical_key
    from app.analysis.skills_canonical import known_variants
    from app.profile import catalogs as _catalogs

    raw = _re.sub(r"\s+", " ", FIXTURE.read_text(
        encoding="utf-8").lower())
    raw_norm = _catalogs.norm_text(raw)
    for item in profile["technical_skills"]:
        options = known_variants(item) or [item]
        assert any(
            _catalogs.norm_text(o) in raw_norm for o in options
        ), f"posible invento: {item}"


def test_sin_warnings_graves():
    warnings = _parsed()["warnings"]
    graves = [w for w in warnings
              if "No se detecto" in w or "no reconocida" in w]
    assert graves == [], graves


def test_otro_formato_ingles_no_sobreajuste():
    from app.cv import pdf_import as pdf

    text = """Jane Doe
Backend Developer
Medellín, Colombia | +57 300 123 4567 | jane@example.com
github.com/janedoe
Professional Summary
Backend developer with experience building REST APIs.
Work Experience
Software Engineer
Jan 2023 – Present
Acme Corp – Medellín
Built APIs with Python and Django for billing.
Education
Master in Computer Science
2021 – 2023
Universidad Nacional – Bogotá
Courses
Python for Everybody – Coursera – 2022
Languages
English – C1
"""
    out = pdf.parse_pdf_profile(text)
    profile = out["profile"]
    assert profile["personal"]["full_name"] == "Jane Doe"
    assert len(profile["experience"]) == 1
    job = profile["experience"][0]
    assert job["company"] == "Acme Corp"
    assert job["is_current"] is True
    assert job["end_date"] is None
    assert "Django" in job["description"]
    assert len(profile["education"]) == 1
    assert profile["education"][0]["level"] == "master"
    assert profile["certifications"][0]["institution"] == "Coursera"
    assert profile["languages"][0]["language"] == "en"
    assert profile["languages"][0]["level"] == "C1"


def test_nombres_compuestos():
    from app.profile import catalogs as _catalogs

    assert _catalogs.split_spanish_name(
        "David Santiago Herrera Reales") == (
        "David Santiago", "Herrera Reales")
    assert _catalogs.split_spanish_name("Ana Torres") == (
        "Ana", "Torres")
    assert _catalogs.split_spanish_name("Luis Herrera Reales") == (
        "Luis Herrera", "Reales")
    assert _catalogs.split_spanish_name("Pedro") == ("Pedro", "")


def test_experiencia_con_skills_tecnicas_y_blandas():
    exp = _parsed()["profile"]["experience"]
    primero = exp[0]
    assert "Python" in primero["technical_skills"]
    assert "Excel" in primero["technical_skills"] or \
        "Excel avanzado" in primero["technical_skills"]
    assert len(primero["technical_skills"]) <= 20
    assert len(primero["soft_skills"]) >= 2
    # Solo lo que la descripcion evidencia ('análisis' -> analitico,
    # 'indicadores' -> resultados). Sin mencion no hay skill.
    assert "Pensamiento analítico" in primero["soft_skills"]
    assert "Trabajo en equipo" not in primero["soft_skills"]
    # Toda skill de la entrada esta evidenciada en su descripcion o
    # titulo (etiqueta canonica o una de sus variantes de signals).
    import re as _re

    from app.analysis import signals as _signals
    from app.profile import catalogs as _catalogs

    variants: dict[str, list[str]] = {}
    for label, aliases, _ in _signals.SKILLS:
        variants.setdefault(label, []).extend([label, *aliases])
    for entry in exp:
        blob = _catalogs.norm_text(
            _re.sub(r"\s+",
                    " ", f"{entry['title']} {entry['description']}"))
        for skill in entry["technical_skills"]:
            options = variants.get(skill, [skill])
            assert any(_catalogs.norm_text(o) in blob for o in options), \
                f"invento en entrada: {skill}"


def _make_pdf_bytes(lines: list[str]) -> bytes:
    """PDF minimo valido con texto (para probar pypdf sin fixtures)."""
    content = b"BT /F1 12 Tf 72 720 Td 14 TL\n"
    for line in lines:
        safe = line.encode("latin-1", errors="replace").replace(
            b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        content += b"(" + safe + b") Tj T*\n"
    content += b"ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
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
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objs) + 1, xref)
    return out


def test_extraccion_bytes_reales_y_endpoint():
    import io

    from fastapi.testclient import TestClient

    from app.cv import pdf_import as pdf
    from app.main import app

    pdf_bytes = _make_pdf_bytes([
        "Ana Torres", "Bogota | ana@example.com",
        "Work Experience", "Support Analyst",
        "Jan 2024 - Dec 2024", "Acme - Bogota",
        "Helped customers with billing issues every day.",
    ])
    assert pdf_bytes.startswith(b"%PDF-")
    text = pdf.extract_pdf_text(pdf_bytes)
    assert "Ana Torres" in text
    assert "Support Analyst" in text

    import app.auth as auth_module

    orig = auth_module.verify_bearer_token
    auth_module.verify_bearer_token = lambda h: {
        "uid": "uid-pdf-import", "email": "x@test.test", "name": "X"}
    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer x"}
            preview = client.post(
                "/profile/import-pdf", files={"file": ("cv.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
                headers=headers)
            assert preview.status_code == 200, preview.text
            body = preview.json()
            assert body["applied"] is False
            assert body["profile"]["personal"]["full_name"] == "Ana Torres"
            assert body["profile"]["experience"][0]["company"] == "Acme"
            applied = client.post(
                "/profile/import-pdf?apply=true",
                files={"file": ("cv.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
                headers=headers)
            assert applied.json()["applied"] is True
            full = client.get("/profile/full", headers=headers).json()
            assert any(e.get("title") == "Support Analyst"
                       for e in full.get("experience", [])), full
            bad = client.post(
                "/profile/import-pdf", files={"file": ("cv.txt", io.BytesIO(b"hola"), "text/plain")},
                headers=headers)
            assert bad.status_code == 400
    finally:
        auth_module.verify_bearer_token = orig
        from app.database.connection import SessionLocal
        from app.database.models import UserProfile, UserRichProfile

        db = SessionLocal()
        try:
            db.query(UserProfile).filter(
                UserProfile.uid == "uid-pdf-import").delete(
                    synchronize_session=False)
            db.query(UserRichProfile).filter(
                UserRichProfile.uid == "uid-pdf-import").delete(
                    synchronize_session=False)
            db.commit()
        finally:
            db.close()
