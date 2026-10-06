"""Sanitizador de palabras pegadas (copiar-desde-PDF).

Repara solo lo anclado a vocabulario tecnico o palabra-comun+numero.
Todo cambio se reporta; el resto del texto queda intacto.
"""


def test_casos_reportados():
    from app.profile.textfix import fix_spacing

    fixed, changes = fix_spacing(
        "más de10.000 registros, utilizandoExcel Avanzado, "
        "Pythonpara limpieza. conocimientos enSQL.")
    assert fixed == ("más de 10.000 registros, utilizando Excel Avanzado, "
                     "Python para limpieza. conocimientos en SQL.")
    assert len(changes) == 4


def test_conserva_tech_y_texto_normal():
    from app.profile.textfix import fix_spacing

    keep = ["JavaScript", "GitHub", "YOLOv8", "utf8", "PowerBI",
            "Node.js", "iOS", "información", "Power BI", "10.000",
            "datos.", "3.5", "SQL,"]
    for token in keep:
        fixed, changes = fix_spacing(token)
        assert fixed == token, token
        assert changes == []


def test_normalize_reporta_cambios():
    from app.profile import schema as profile_schema

    profile, warnings = profile_schema.normalize_rich_profile({
        "professional_summary": "Experto utilizandoExcel y Pythonpara datos.",
        "experience": [{
            "title": "Dev", "company": "Acme",
            "description": "Trabajo con datos de10.000 filas.",
        }],
    })
    assert "utilizando Excel" in profile["professional_summary"]
    assert "de 10.000 filas" in profile["experience"][0]["description"]
    assert any("palabras pegadas" in w for w in warnings)


def test_pipeline_no_pega_espacios():
    """El renderer reproduce byte a byte: si entra limpio, sale limpio."""
    from app.adapt import html_renderer as html

    import re as _re

    summary = ("bases de datos de más de 10.000 registros, utilizando "
               "Excel Avanzado y Python para limpieza.")
    out = html.render_cv_html(
        {"full_name": "T", "summary": summary, "experiences": []},
        None, {"font_size_pt": 11})
    body = _re.search(r"summary\">(.*?)</p>", out, _re.S).group(1)
    assert body == summary
