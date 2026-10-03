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
    # Meses en español si se aceptan (fixture del perfil demo los usa).
    assert profile_schema.normalize_date("Sep 2026") == "2026-09-01"
    assert profile_schema.normalize_date("marzo 2025") == "2025-03-01"
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


def test_seniority_and_sector_normalization():
    assert catalogs.norm_seniority("Junior")["id"] == "junior"
    assert catalogs.norm_seniority("SEMI-SENIOR")["id"] == "mid"
    assert catalogs.norm_seniority("Semi Senior")["id"] == "mid"
    assert catalogs.norm_seniority("semi-senior")["id"] == "mid"
    assert catalogs.norm_seniority("Dios de los datos") is None
    assert catalogs.norm_seniority("") is None
    assert catalogs.norm_sector("Tecnología")["id"] == "tecnologia"
    assert catalogs.norm_sector("tecnologia")["id"] == "tecnologia"
    assert catalogs.norm_sector("Servicios Financieros")["id"] == "finanzas"
    assert catalogs.norm_sector("banca")["id"] == "finanzas"
    assert catalogs.norm_sector("Retail")["id"] == "comercio"
    assert catalogs.norm_sector("Sector publico")["id"] == "gobierno"
    assert catalogs.norm_sector("Astrologia") is None


def test_salary_currency_and_period():
    assert catalogs.norm_salary_currency("cop") == "COP"
    assert catalogs.norm_salary_currency("COP ($)") == "COP"
    assert catalogs.norm_salary_currency("XXX") is None
    assert catalogs.norm_salary_period("Mensual") == "mensual"
    assert catalogs.norm_salary_period("mensual") == "mensual"
    assert catalogs.norm_salary_period("quincenal") is None


def test_parse_and_format_salary():
    parsed = profile_schema.parse_salary("3500000 COP mensual")
    assert parsed["amount"] == 3500000
    assert parsed["currency"] == "COP"
    assert parsed["period"] == "mensual"
    assert profile_schema.parse_salary("")["amount"] is None
    assert profile_schema.parse_salary(None)["amount"] is None
    # Numero suelto: no inventa moneda ni periodo.
    solo = profile_schema.parse_salary("3500000")
    assert solo["amount"] == 3500000
    assert solo["currency"] is None
    assert profile_schema.format_salary(3500000, "COP", "mensual") == (
        "3500000 COP mensual"
    )
    assert profile_schema.format_salary(None, None, None, "texto") == "texto"


def test_normalize_flat_profile_collapses_variants():
    profile, warnings = profile_schema.normalize_flat_profile({
        "modality": "hibrido",
        "experience_level": "Semi Senior",
        "target_roles": ["analista datos", "Astronauta"],
        "sectors": ["banca", "Retail"],
        "location": "Bogotá, Colombia",
        "preferred_location": "BOGOTA",
        "min_salary": "3500000 COP mensual",
        "skills": ["Power BI", "power bi", "SQL"],
    })
    assert profile["modality"] == "HYBRID"
    assert profile["experience_level"] == "mid"
    # Cargo en catalogo se canoniza; fuera de catalogo se conserva.
    assert profile["target_roles"] == ["Analista de Datos", "Astronauta"]
    assert profile["sectors"] == ["Servicios Financieros", "Comercio / Retail"]
    assert profile["location"] == "Bogotá"
    assert profile["preferred_location"] == "Bogotá"
    assert profile["min_salary"] == "3500000 COP mensual"
    # Skills de-duplicadas sin tildes/mayusculas.
    assert profile["skills"] == ["Power BI", "SQL"]
    assert any("Astronauta" in w for w in warnings)


def test_normalize_flat_profile_bad_modality_warns():
    profile, warnings = profile_schema.normalize_flat_profile({
        "modality": "desde la playa",
    })
    assert profile["modality"] == "desde la playa"
    assert any("Modalidad" in w for w in warnings)


def test_normalize_flat_profile_salary_structured():
    profile, _ = profile_schema.normalize_flat_profile({
        "min_salary": "3000000",
        "min_salary_currency": "USD",
        "min_salary_period": "anual",
    })
    assert profile["min_salary"] == "3000000 USD anual"
    assert "min_salary_currency" not in profile
    assert "min_salary_period" not in profile


def test_save_profile_normalizes_flat():
    from fastapi.testclient import TestClient

    from app.main import app

    # save_profile necesita una Session de SQLAlchemy; el endpoint
    # /profile sin token usa el perfil global y ejercita el mismo camino.
    with TestClient(app) as client:
        original = client.get("/profile").json()
        try:
            response = client.put("/profile", json={
                "full_name": "Test",
                "modality": "remoto",
                "experience_level": "Semi Senior",
                "target_roles": ["data analyst"],
                "sectors": ["banca"],
                "min_salary": "4500000 COP mensual",
            })
            assert response.status_code == 200
            body = response.json()
            assert body["modality"] == "REMOTE"
            assert body["experience_level"] == "mid"
            assert body["target_roles"] == ["Analista de Datos"]
            assert body["sectors"] == ["Servicios Financieros"]
            assert body["min_salary"] == "4500000 COP mensual"
        finally:
            client.put("/profile", json=original)


def test_catalogs_endpoint():
    with TestClient(app) as client:
        response = client.get("/catalogs")
        assert response.status_code == 200
        body = response.json()
        assert "professional_titles" in body
        assert "cities" in body
        assert any(c["id"] == "bogota" for c in body["cities"])
        assert body["cities"][0]["id"] == "bogota"
        # Catalogos nuevos que consume la UI para los desplegables.
        for key in ("seniority_levels", "sectors", "salary_currencies",
                    "salary_periods"):
            assert key in body, key
            assert len(body[key]) > 0, key
        assert any(
            s["id"] == "senior" for s in body["seniority_levels"]
        )
        assert any(s["id"] == "tecnologia" for s in body["sectors"])
        assert any(c["id"] == "COP" for c in body["salary_currencies"])


def test_catalogs_no_duplicates_extended():
    catalogs_data = catalogs.get_catalogs()
    for name in ("seniority_levels", "sectors", "salary_currencies",
                 "salary_periods", "entry_status", "contract_types",
                 "modalities", "education_levels", "language_levels"):
        labels = [c["label"] for c in catalogs_data[name]]
        ids = [c["id"] for c in catalogs_data[name]]
        assert len(ids) == len(set(ids)), name
        lowered = [catalogs.norm_text(label) for label in labels]
        assert len(lowered) == len(set(lowered)), name
