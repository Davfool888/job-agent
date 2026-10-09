"""Evaluacion legible oferta-vs-perfil (pura, sin BD)."""
from app.analysis.verdict import build_fit_report
from app.analysis.verdict import level_for_score
from app.analysis.verdict import split_tech_soft


def _analysis(**over):
    base = {
        "match_score": 72.0,
        "matched_skills": ["Power BI", "SQL", "Comunicación"],
        "missing_skills": ["Python", "Liderazgo"],
        "experience_required": "2 año(s) de experiencia",
        "category": "DATA_ANALYST",
        "detected_role": "Data Analyst",
        "score_breakdown": {"title": 12, "skills": 20,
                            "responsibilities": 18, "tools": 10},
    }
    base.update(over)
    return base


def _profile():
    return {"skills": ["Power BI", "SQL", "Python", "Comunicación",
                       "Liderazgo"],
            "target_roles": ["Data Analyst"],
            "years_experience": 3}


def test_niveles_por_banda():
    assert level_for_score(80)[0] == "muy_compatible"
    assert level_for_score(60)[0] == "compatible"
    assert level_for_score(45)[0] == "parcial"
    assert level_for_score(10)[0] == "poco_compatible"
    assert level_for_score(None)[0] == "sin_datos"


def test_separa_tecnicas_y_blandas():
    tech, soft = split_tech_soft(["Power BI", "Comunicación", "Liderazgo",
                                  "SQL", "Power BI"])
    assert tech == ["Power BI", "SQL"]
    assert soft == ["Comunicación", "Liderazgo"]


def test_reporte_dimensiones_y_veredicto():
    job = {"title": "Analista de Datos",
           "description": "Power BI SQL Python 2 años de experiencia",
           "requirements": "", "responsibilities": ""}
    rich = {"technical_skills": ["Power BI", "SQL"],
            "soft_skills": ["Comunicación"],
            "years_experience": 3, "target_roles": ["Data Analyst"]}
    report = build_fit_report(job, _analysis(), _profile(), rich)
    assert report["level"] == "compatible"
    dims = report["dimensions"]
    assert dims["tecnicas"]["matched"] == ["Power BI", "SQL"]
    assert dims["tecnicas"]["missing"] == ["Python"]
    assert dims["tecnicas"]["coverage"] == 67
    assert dims["blandas"]["matched"] == ["Comunicación"]
    assert dims["blandas"]["missing"] == ["Liderazgo"]
    assert dims["blandas"]["coverage"] == 50
    assert dims["experiencia"]["fit"] == "justo"
    assert dims["experiencia"]["required_years"] == 2
    assert dims["puesto"]["match"] is True
    assert dims["puesto"]["matched_target"] == "Data Analyst"
    assert report["strengths"] and report["gaps"]
    assert any("67%" in r for r in report["reasons"])


def test_experiencia_corta_y_rol_fuera():
    job = {"title": "Senior", "description": "5 años de experiencia",
           "requirements": "", "responsibilities": ""}
    analysis = _analysis(match_score=30.0, category="OTHER",
                         detected_role=None)
    rich = {"technical_skills": [], "soft_skills": [],
            "years_experience": 1, "target_roles": ["Data Analyst"]}
    report = build_fit_report(job, analysis, _profile(), rich)
    assert report["level"] == "poco_compatible"
    assert report["dimensions"]["experiencia"]["fit"] == "corto"
    assert report["dimensions"]["puesto"]["match"] is False
    assert any("faltan" in g for g in report["gaps"])


def test_sin_datos_no_revienta():
    report = build_fit_report({}, {}, {}, {})
    assert report["level"] == "sin_datos"
    assert report["dimensions"]["tecnicas"] == {
        "matched": [], "missing": [], "coverage": None}
    assert report["dimensions"]["experiencia"]["fit"] == "sin_dato"
    report = build_fit_report(None, None, None, None)
    assert report["level"] == "sin_datos"
