"""Preprocesado de espaciado del CV adaptado (casos reales)."""
from app.adapt.textclean import clean_content
from app.adapt.textclean import clean_text


def test_colapsa_y_puntua():
    assert clean_text("info   con    espacios") == "info con espacios"
    assert clean_text("duplicados,filtrado y segmentación") == \
        "duplicados, filtrado y segmentación"
    assert clean_text("General:Analizar información") == \
        "General: Analizar información"
    assert clean_text("decisiones.Analicé datos") == \
        "decisiones. Analicé datos"
    assert clean_text("Demanda(en desarrollo)") == "Demanda (en desarrollo)"
    # Decimales, rangos, horas y URLs intactos.
    assert clean_text("más de 10.000 registros") == "más de 10.000 registros"
    assert clean_text("entre 30-40 en seguimiento") == \
        "entre 30-40 en seguimiento"
    # Handles, niveles y versiones intactos.
    assert clean_text("github.com/Davfool888") == "github.com/Davfool888"
    assert clean_text("Python3, EC2 y nivel b2") == "Python3, EC2 y nivel b2"


def test_fronteras_mecanicas():
    assert clean_text("informaciónEmpresarial y Comercial") == \
        "información Empresarial y Comercial"
    # 'registrosutilizando' (minuscula+minuscula sin frontera) NO se puede
    # partir sin diccionario: se conserva y debe corregirse en el origen.
    assert clean_text("10.000 registrosutilizando Excel") == \
        "10.000 registrosutilizando Excel"
    assert clean_text("10.000registros utilizando Excel") == \
        "10.000 registros utilizando Excel"
    assert clean_text("Desarrollé una aplicación enPythonpara consultar") == \
        "Desarrollé una aplicación en Python para consultar"
    assert clean_text("Empresas Cooperativas– Análisis") == \
        "Empresas Cooperativas – Análisis"
    # Keep-list y nombres intactos.
    assert clean_text("YOLOv8, OpenCV y utf8") == "YOLOv8, OpenCV y utf8"
    assert clean_text("diseño 3D y APIs REST") == "diseño 3D y APIs REST"
    assert clean_text("PowerBI y McDonald") == "PowerBI y McDonald"


def test_corte_guion_por_salto_de_linea():
    assert clean_text("tareas de procesa- miento, organización") == \
        "tareas de procesamiento, organización"
    assert clean_text("entre 30-40 en seguimiento") == \
        "entre 30-40 en seguimiento"
    assert clean_text("03/2025 – 12/2025") == "03/2025 – 12/2025"


def test_vocales_partidas():
    assert clean_text("Gestion é y validé información") == \
        "Gestioné y validé información"
    assert clean_text("Consulté y realicé seguimiento") == \
        "Consulté y realicé seguimiento"


def test_idempotente():
    once = clean_text("General:Analizar info.Empresas Cooperativas– X")
    assert clean_text(once) == once


def test_limpia_content_sin_tocar_identidad():
    content = {
        "full_name": "David Herrera",
        "email": "a@b.co",
        "summary": "Analista  con   datos.",
        "experiences": [{
            "title": "Ejecutivo–Nómina",
            "company": "Banco de Bogotá",
            "description": "General:Analizar info.",
            "bullets": ["Consulté  datos."],
        }],
    }
    out = clean_content(content)
    assert out["full_name"] == "David Herrera"
    assert out["email"] == "a@b.co"
    assert out["summary"] == "Analista con datos."
    assert out["experiences"][0]["title"] == "Ejecutivo – Nómina"
    assert out["experiences"][0]["company"] == "Banco de Bogotá"
    assert out["experiences"][0]["description"] == "General: Analizar info."
    assert out["experiences"][0]["bullets"] == ["Consulté datos."]


def test_renderer_no_duplica_etiqueta():
    from app.adapt.html_renderer import _experience_block

    html = _experience_block({"experiences": [{
        "title": "X",
        "description": "Responsabilidad General:Analizar información.",
    }]})
    assert html.count("Responsabilidad General:") == 1
    assert "Responsabilidad General:</strong> Analizar" in html
