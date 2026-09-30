"""Perfil modular con perspectivas: scoring, seleccion, no-invencion."""
from fastapi.testclient import TestClient

from app.main import app
from app.profile.perspectives import build_tailored_profile
from app.profile.perspectives import flatten_profile_skills
from app.profile.perspectives import score_perspective
from app.profile.perspectives import select_perspectives
from app.profile.perspectives import validate_profile

BANCO = {
    "id": "exp-banco-1",
    "title": "Ejecutivo de Nómina para Empresas Cooperativas",
    "company": "Banco de Bogotá",
    "period": "2021 - 2024",
    "perspectives": [
        {
            "id": "comercial",
            "label": "Comercial",
            "description": "Contacto con empresas y fidelizacion.",
            "skills": ["Gestión comercial"],
            "tools": ["Excel"],
            "domains": ["banking"],
            "roles": ["BUSINESS_ANALYST"],
        },
        {
            "id": "data",
            "label": "Data Analytics",
            "description": "Bases de datos con miles de registros, depuracion y cruces.",
            "skills": ["Power BI", "Excel avanzado", "Data Cleaning", "ETL"],
            "tools": ["Power BI", "Python", "Excel"],
            "domains": ["banking", "finance"],
            "roles": ["DATA_ANALYST", "BI_ANALYST"],
        },
    ],
}

PROFILE = {
    "personal": {"full_name": "Test User"},
    "skills": ["Python", "Power BI", "DAX", "SQL", "Excel", "Excel avanzado",
               "Data Cleaning", "ETL", "Gestión comercial"],
    "target_roles": ["Data Analyst"],
    "experience": [BANCO],
    "education": [],
    "projects": [],
}

JOB_DATA = {
    "title": "Analista de Datos",
    "description": "Power BI, DAX, SQL, Excel, análisis de cartera, "
                   "indicadores financieros, experiencia con empresas. "
                   "Sector financiero.",
    "sector": "financiero",
}
ANALYSIS_DATA = {
    "category": "DATA_ANALYST",
    "detected_role": "Data Analyst",
    "evidence": ["Power BI", "DAX", "SQL", "indicadores"],
}


def test_flatten_incluye_perspectivas_y_es_compatible():
    flat = flatten_profile_skills({"skills": ["Python", "SQL"]})
    assert flat == ["Python", "SQL"]
    flat2 = flatten_profile_skills(PROFILE)
    assert "Power BI" in flat2 and "ETL" in flat2
    assert len(flat2) == len(set(flat2))


def test_perspectiva_data_gana_para_vacante_datos():
    from app.profile.perspectives import extract_job_signals

    signals = extract_job_signals(JOB_DATA, ANALYSIS_DATA)
    data = next(p for p in BANCO["perspectives"] if p["id"] == "data")
    com = next(p for p in BANCO["perspectives"] if p["id"] == "comercial")
    score_data = score_perspective(data, signals)
    score_com = score_perspective(com, signals)
    assert score_data["relevance_score"] > score_com["relevance_score"]
    assert "Power BI" in score_data["matched_skills"]
    assert "banking" in score_data["matched_domain"]
    assert set(score_data["breakdown"]) == {
        "role_match", "skills_match", "industry_match",
        "domain_match", "experience_match", "tools_match",
    }


def test_seleccion_combina_perspectivas_sin_inventar():
    selection = select_perspectives(PROFILE, JOB_DATA, ANALYSIS_DATA)
    assert selection["selection"]
    best = selection["selection"][0]
    assert best["perspective"] == "Data Analytics"
    assert best["relevance_score"] >= 50
    tailored = build_tailored_profile(PROFILE, selection, JOB_DATA,
                                      ANALYSIS_DATA)
    assert tailored["adapted"] is True
    assert tailored["personal"]["full_name"] == "Test User"
    # Todo el texto viene del perfil: ninguna palabra externa.
    corpus = " ".join([
        PROFILE["personal"]["full_name"],
        BANCO["title"], BANCO["company"],
        *[p["description"] for p in BANCO["perspectives"]],
        *[s for p in BANCO["perspectives"] for s in p["skills"]],
    ]).lower()
    for block in tailored["blocks"]:
        assert block["description"].lower() in corpus
        for skill in block["skills"]:
            assert skill.lower() in corpus


def test_validate_avisa_skills_no_declarados():
    profile = {"skills": ["Python"],
               "experience": [{
                   "title": "X",
                   "perspectives": [{
                       "id": "p1", "label": "L1",
                       "skills": ["AWS SalchichaInventada"],
                       "tools": [], "domains": [], "roles": [],
                       "description": "",
                   }],
               }]}
    warnings = validate_profile(profile)
    assert any("AWS SalchichaInventada" in w for w in warnings)
    assert validate_profile(PROFILE) == []


def test_match_score_integra_bonus_acotado():
    from app.analysis.scorer import analyze_job

    job = {"title": "Analista de Datos en empresa financiera",
           "description": JOB_DATA["description"]}
    result = analyze_job(job, PROFILE)
    assert result["category"] in ("DATA_ANALYST", "BI_ANALYST")
    assert 0.0 <= result.get("perspective_bonus", 0.0) <= 8.0
    assert result["top_perspectives"]
    assert result["top_perspectives"][0]["perspective"] == "Data Analytics"
    # Sin perspectivas no hay bonus (compatibilidad).
    plain = analyze_job(job, {"skills": ["Python"],
                              "target_roles": ["Data Analyst"]})
    assert plain.get("perspective_bonus", 0.0) == 0.0
    assert plain["match_score"] <= result["match_score"]


def test_tailor_endpoint():
    from app.config import BASE_CV_PATH
    from app.database.connection import SessionLocal
    from app.database.models import Job
    from app.services.job_service import save_jobs

    backup = (
        BASE_CV_PATH.read_text(encoding="utf-8")
        if BASE_CV_PATH.exists() else None
    )
    db = SessionLocal()
    try:
        saved = save_jobs(db, [{
            "title": "Analista de Datos sector financiero",
            "company": "Banco Prueba",
            "url": "https://example.com/tailor-1",
            "description": JOB_DATA["description"],
            "source": "computrabajo",
        }])
        job_id = saved[0].id
    finally:
        db.close()
    try:
        with TestClient(app) as client:
            put_response = client.put("/profile/full", json=PROFILE)
            assert put_response.status_code == 200
            response = client.post(f"/jobs/{job_id}/tailor")
            assert response.status_code == 200
            body = response.json()
            assert body["tailored_profile"]["adapted"] is True
            assert body["selection"] != []
            assert body["selection"][0]["perspective"] == "Data Analytics"
            assert "combined_skills" in body
    finally:
        if backup is not None:
            BASE_CV_PATH.write_text(backup, encoding="utf-8")
        db = SessionLocal()
        db.query(Job).filter(
            Job.url == "https://example.com/tailor-1"
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
