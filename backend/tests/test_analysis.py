"""Sistema de descubrimiento y scoring por capas (§1-§20)."""
from fastapi.testclient import TestClient

from app.agents.job_analyzer import JobAnalyzer
from app.analysis.scorer import analyze_job
from app.main import app

AUXILIAR_MOTO = {
    "title": "Auxiliar con moto",
    "description": (
        "Responsable de consolidar información proveniente de diferentes "
        "fuentes, realizar limpieza de bases de datos, generar informes "
        "y dashboards utilizando Power BI y Excel. Elaboración de "
        "indicadores y análisis de bases de datos. Requisitos: Excel "
        "avanzado, manejo de Power BI, 1 año de experiencia en análisis "
        "de información."
    ),
}

VENDEDOR_EXCEL = {
    "title": "Vendedor con moto",
    "description": (
        "Se requiere vendedor con conocimientos básicos de Excel y "
        "computador para atención al cliente en punto de venta. "
        "Experiencia en ventas."
    ),
}

PROFILE = {
    "skills": ["Python", "SQL", "Power BI", "Excel", "Pandas"],
    "target_roles": ["Data Analyst", "BI"],
}


def test_auxiliar_con_moto_es_data_analyst():
    result = analyze_job(AUXILIAR_MOTO, PROFILE)
    assert result["category"] == "DATA_ANALYST"
    assert result["detected_role"] == "Data Analyst"
    assert result["match_score"] >= 60
    evidence = " ".join(result["evidence"]).lower()
    assert "power bi" in evidence
    assert "SQL" in result["missing_skills"]
    assert "Power BI" in result["matched_skills"]
    assert result["experience_required"] == "1 año(s) de experiencia"


def test_vendedor_con_excel_no_es_data():
    # §12: una sola evidencia debil NUNCA clasifica.
    result = analyze_job(VENDEDOR_EXCEL, PROFILE)
    assert result["category"] == "OTHER"
    assert result["detected_role"] is None
    assert result["match_score"] < 25


def test_titulo_solo_clasifica_sin_inflarlo():
    result = analyze_job({"title": "Analista de Datos", "description": ""}, PROFILE)
    assert result["category"] == "DATA_ANALYST"
    # Sin descripcion no hay señales de contenido: score modesto.
    assert result["match_score"] <= 30


def test_descripcion_vacia_no_falla():
    result = analyze_job({"title": "", "description": ""}, PROFILE)
    assert result["match_score"] == 0
    assert result["category"] == "OTHER"


def test_analyzer_retrocompatible():
    out = JobAnalyzer().analyze(AUXILIAR_MOTO, PROFILE)
    assert out["job_title"] == "Auxiliar con moto"
    assert out["relevant"] is True
    assert out["match_score"] >= 60
    assert out["ai_enriched"] is False


def test_discovery_dedup_y_discovered_by():
    client = TestClient(app)
    with client:
        base = {
            "title": "Oferta Sintetica Analisis XYZ",
            "company": "Empresa Prueba Analisis",
            "location": "Bogota",
            "url": "https://example.com/analisis-1",
            "description": AUXILIAR_MOTO["description"],
            "source": "computrabajo",
        }
        from app.database.connection import SessionLocal
        from app.database.models import Job
        from app.services.job_service import refresh_job
        from app.services.job_service import save_jobs
        from app.analysis.discovery import _tag_discovered

        db = SessionLocal()
        try:
            first = save_jobs(db, [base], search_query="power bi")
            _tag_discovered(db, [first[0].id], "power-bi")
            # Segunda query distinta, misma URL -> sin duplicado.
            second = save_jobs(db, [base], search_query="analista de datos")
            _tag_discovered(db, [second[0].id], "analista-de-datos")
            assert first[0].id == second[0].id
            fresh = refresh_job(db, first[0])
            import json

            discovered = fresh.discovered_by
            if isinstance(discovered, str):
                discovered = json.loads(discovered)
            assert discovered == [
                "power-bi",
                "analista-de-datos",
            ]
        finally:
            db.query(Job).filter(
                Job.url == "https://example.com/analisis-1"
            ).delete(synchronize_session=False)
            db.commit()
            db.close()


def test_endpoint_analyze():
    with TestClient(app) as client:
        jobs = client.get("/jobs", params={"limit": 1}).json()
        if not jobs:
            return  # sin datos: el e2e manual lo cubre
        job_id = jobs[0]["id"]
        response = client.post(f"/jobs/{job_id}/analyze")
        assert response.status_code == 200
        body = response.json()
        assert "analysis" in body
        assert "match_score" in body["analysis"]
        assert "evidence" in body["analysis"]
