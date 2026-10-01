"""Perfil estructurado: catalogos, normalizacion y persistencia."""
from fastapi.testclient import TestClient

from app.main import app
from app.profile import catalogs
from app.profile import schema as profile_schema
from app.profile.perspectives import flatten_profile_skills


def test_catalogs_no_duplicates():
    catalogs_data = catalogs.get_catalogs()
    for name in ("professional_titles", "cities", "languages"):
        labels = [c["label"] for c in catalogs_data[name]]
        ids = [c["id"] for c in catalogs_data[name]]
        assert len(ids) == len(set(ids)), name
        lowered = [catalogs.norm_text(label) for label in labels]
        assert len(lowered) == len(set(lowered)), name


def test_title_normalization():
    assert catalogs.norm_title("Data Analyst")["id"] == "data_analyst"
    assert catalogs.norm_title("data analyst")["id"] == "data_analyst"
    assert catalogs.norm_title("ANALISTA DE DATOS")["id"] == "data_analyst"
    assert catalogs.norm_title("Astronauta") is None
    assert catalogs.norm_title("") is None
    assert catalogs.norm_title("  ") is None


def test_city_normalization():
    bogota = catalogs.norm_city("Bogotá D.C.")
    assert bogota is not None and bogota["id"] == "bogota"
    assert bogota["country"] == "CO"
    assert catalogs.norm_city("bogota")["id"] == "bogota"
    assert catalogs.norm_city("BOGOTA")["id"] == "bogota"
    assert catalogs.norm_city("Medellín, Colombia")["id"] == "medellin"
    assert catalogs.norm_city("Atlantis") is None
    assert catalogs.norm_city("") is None


def test_modality_normalization():
    assert catalogs.norm_modality("Híbrido") == "HYBRID"
    assert catalogs.norm_modality("remoto") == "REMOTE"
    assert catalogs.norm_modality("PRESENCIAL") == "ONSITE"
    assert catalogs.norm_modality("REMOTE") == "REMOTE"
    assert catalogs.norm_modality("desde la playa") is None
    assert catalogs.norm_modality("") is None


def test_language_level_strict():
    assert catalogs.norm_language_level("B1") == "B1"
    assert catalogs.norm_language_level("nativo") == "native"
    assert catalogs.norm_language_level("intermedio") is None
    assert catalogs.norm_language_level("B1+") is None
    assert catalogs.norm_language_level("") is None
    assert catalogs.norm_language("Inglés")["id"] == "en"
    assert catalogs.norm_language("ingles")["id"] == "en"


def test_normalize_date():
    assert profile_schema.normalize_date("2022-04-15") == "2022-04-15"
    assert profile_schema.normalize_date("2022-4") == "2022-04-01"
    assert profile_schema.normalize_date("abril de 2022") is None
    assert profile_schema.normalize_date("2022-2026") is None
    assert profile_schema.normalize_date("Sep 2026") is None
    assert profile_schema.normalize_date("") is None
    assert profile_schema.normalize_date(None) is None
    assert profile_schema.normalize_date("2022-13-01") is None


def test_years_experience_numeric():
    profile, warnings = profile_schema.normalize_rich_profile(
        {"years_experience": 2})
    assert profile["years_experience"] == 2.0
    profile, _ = profile_schema.normalize_rich_profile(
        {"years_experience": "2.5"})
    assert profile["years_experience"] == 2.5
    profile, warnings = profile_schema.normalize_rich_profile(
        {"years_experience": "2 años"})
    assert profile["years_experience"] is None
    assert any("years_experience" in w for w in warnings)


def test_experience_entry_structured():
    entry, warnings = profile_schema.normalize_entry("experience", {
        "company": "Banco de Bogotá",
        "title": "Ejecutivo de Nómina",
        "start_date": "2023-10-01",
        "is_current": True,
        "end_date": "2030-01-01",
        "modality": "Híbrido",
        "city": "Bogotá D.C.",
        "technical_skills": ["Power BI", "DAX"],
        "soft_skills": ["Comunicación"],
    })
    assert entry["end_date"] is None  # is_current manda, sin fecha ficticia
    assert entry["is_current"] is True
    assert entry["modality"] == "HYBRID"
    assert entry["city"] == {"id": "bogota", "label": "Bogotá",
                             "country": "CO"}
    assert entry["start_date"] == "2023-10-01"
    assert entry["technical_skills"] == ["Power BI", "DAX"]
    assert entry["soft_skills"] == ["Comunicación"]
    assert warnings == []


def test_experience_bad_modality_warns():
    _, warnings = profile_schema.normalize_entry("experience", {
        "company": "X", "modality": "desde la playa"})
    assert any("Modalidad" in w for w in warnings)


def test_language_entry_structured():
    entry, warnings = profile_schema.normalize_language({
        "language": "Inglés",
        "academy": "Smart",
        "level": "B1",
        "listening": "B1",
        "reading": "B1",
        "writing": "intermedio",
        "speaking": "A2",
    })
    assert entry["language"] == "en"
    assert entry["writing"] is None
    assert entry["speaking"] == "A2"
    assert any("intermedio" in w for w in warnings)


def test_personal_split_and_title():
    personal, warnings = profile_schema.normalize_personal({
        "full_name": "Ana María Torres",
        "title": "data analyst",
        "email": "a@b.co",
    })
    assert personal["first_name"] == "Ana"
    assert personal["last_name"] == "María Torres"
    assert personal["full_name"] == "Ana María Torres"
    assert personal["title_id"] == "data_analyst"
    assert personal["title"] == "Analista de Datos"
    assert warnings == []


def test_flatten_includes_technical_soft():
    profile = {
        "skills": [],
        "technical_skills": ["Power BI"],
        "soft_skills": ["Comunicación"],
        "experience": [{
            "title": "X",
            "technical_skills": ["DAX"],
            "soft_skills": ["Liderazgo"],
            "perspectives": [],
        }],
    }
    flat = flatten_profile_skills(profile)
    assert "Power BI" in flat
    assert "Comunicación" in flat
    assert "DAX" in flat
    assert "Liderazgo" in flat


def test_save_rich_profile_normalizes_and_roundtrips():
    from app.config import BASE_CV_PATH
    from app.services.job_service import save_rich_profile

    backup = (
        BASE_CV_PATH.read_text(encoding="utf-8")
        if BASE_CV_PATH.exists() else None
    )
    try:
        out = save_rich_profile({
            "personal": {"full_name": "Test User",
                         "title": "ANALISTA DE DATOS"},
            "years_experience": 3,
            "technical_skills": ["Power BI"],
            "experience": [{
                "company": "Banco Test",
                "title": "Analista",
                "start_date": "2022-04",
                "is_current": True,
                "modality": "Remoto",
                "city": "bogota",
                "technical_skills": ["SQL"],
                "soft_skills": ["Comunicación"],
            }],
            "languages": [{
                "language": "Inglés", "level": "B1",
                "listening": "B1", "reading": "B1",
                "writing": "A2", "speaking": "A2",
            }],
        })
        profile = out["profile"]
        assert profile["personal"]["first_name"] == "Test"
        assert profile["personal"]["title_id"] == "data_analyst"
        assert profile["years_experience"] == 3.0
        exp = profile["experience"][0]
        assert exp["start_date"] == "2022-04-01"
        assert exp["end_date"] is None
        assert exp["modality"] == "REMOTE"
        assert exp["city"]["id"] == "bogota"
        assert profile["languages"][0]["language"] == "en"
        assert profile["languages"][0]["speaking"] == "A2"
    finally:
        if backup is None:
            if BASE_CV_PATH.exists():
                BASE_CV_PATH.unlink()
        else:
            BASE_CV_PATH.write_text(backup, encoding="utf-8")


def test_catalogs_endpoint():
    with TestClient(app) as client:
        response = client.get("/catalogs")
        assert response.status_code == 200
        body = response.json()
        assert "professional_titles" in body
        assert "cities" in body
        assert any(c["id"] == "bogota" for c in body["cities"])
        assert body["cities"][0]["id"] == "bogota"
