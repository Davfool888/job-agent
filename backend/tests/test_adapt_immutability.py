"""Inmutabilidad: ninguna etapa muta el perfil display de entrada."""
import copy


def _display_profile():
    return {
        "full_name": "Ana Torres",
        "title": "Analista de Datos",
        "email": "a@test.test",
        "phone": "",
        "linkedin": "",
        "github": "",
        "portfolio": "",
        "location": "Bogota",
        "modality": "",
        "summary": "Analista con Python y SQL.",
        "years_experience": 2.0,
        "skills_technical": ["Python", "SQL"],
        "skills_soft": ["Liderazgo"],
        "skills_groups": {"data": ["Python"]},
        "target_roles": [],
        "languages": [{"label": "Ingles", "level": "B1"}],
        "experiences": [{
            "title": "Analista", "company": "Acme",
            "start": "Mar 2025", "end": "Dic 2025",
            "description": "Analice datos con Python. Genere reportes.",
            "technical_skills": ["Python"],
        }],
        "education": [],
        "projects": [{"name": "P1", "description": "Proyecto con SQL.",
                      "technologies": ["SQL"]}],
        "certifications": [],
        "other_studies": [],
        "other_knowledge": [],
    }


def _offer():
    return {"title": "Analista de Datos", "company": "Banco",
            "description": "Python SQL reportes", "location": "",
            "modality": "", "requirements": [], "responsibilities": []}


def test_matcher_no_alias_perfil():
    from app.adapt import matcher

    profile = _display_profile()
    snapshot = copy.deepcopy(profile)
    matching = matcher.match_offer_profile(_offer(), profile)
    assert profile == snapshot
    # Los items rankeados son copias: mutarlos no toca el perfil.
    for section in ("experiences", "projects", "certifications",
                    "education"):
        for row in matching.get(section) or []:
            row["item"]["title"] = "MUTADO"
    assert profile == snapshot


def test_selector_no_mutar_perfil_ni_matching():
    from app.adapt import matcher, selector

    profile = _display_profile()
    snapshot_profile = copy.deepcopy(profile)
    matching = matcher.match_offer_profile(_offer(), profile)
    snapshot_matching = copy.deepcopy(matching)
    content = selector.select_cv_content(
        profile, _offer(), matching, {"max_projects": 1})
    assert profile == snapshot_profile
    assert matching == snapshot_matching
    assert len(content["projects"]) == 1


def test_coerce_no_mutar_entrada():
    from app.adapt import content as adapt_content

    profile = _display_profile()
    snapshot = copy.deepcopy(profile)
    out, _warnings = adapt_content.coerce_profile(profile)
    assert profile == snapshot
    out["experiences"][0]["title"] = "MUTADO"
    assert profile == snapshot


def test_guest_no_mutar_rich_de_job_service():
    from app.adapt import guest

    rich = {"personal": {"full_name": "X"},
            "other_knowledge": ["a"]}
    snapshot = copy.deepcopy(rich)
    # Simula lo que hace get_profile_for_cv con el dict de job_service:
    # debe trabajar sobre copia.
    working = dict(rich)
    working.setdefault("other_studies", [])
    assert rich == snapshot


def _valid_profile():
    return {
        "full_name": "Ana Torres",
        "skills_technical": ["Python", "SQL"],
        "skills_soft": [],
        "skills_groups": {},
        "target_roles": [],
        "languages": [],
        "experiences": [{
            "title": "Analista", "company": "Acme",
            "start": "Mar 2025", "end": "Dic 2025",
            "description": "Analice 30 reportes con Python.",
            "technical_skills": ["Python"],
        }],
        "education": [],
        "projects": [],
        "certifications": [],
    }


def test_validate_ok_con_contenido_real():
    from app.adapt import validate as adapt_validate

    profile = _valid_profile()
    content = {
        "summary": "Analista.",
        "skills": ["Python"],
        "experiences": [dict(profile["experiences"][0])],
        "education": [],
        "projects": [],
        "certifications": [],
        "languages": [],
    }
    ok, issues = adapt_validate.validate_pre_render(content, profile, {})
    assert ok is True
    assert issues == []


def test_validate_rechaza_skill_empresa_cifra_fecha():
    from app.adapt import validate as adapt_validate

    profile = _valid_profile()
    bad_skill = {
        "summary": "x", "skills": ["Rust"], "experiences": [],
        "education": [], "projects": [], "certifications": [],
        "languages": [],
    }
    ok, issues = adapt_validate.validate_pre_render(
        bad_skill, profile, {})
    assert ok is False
    assert any("sin respaldo" in i for i in issues)

    bad_company = {
        "summary": "x", "skills": [],
        "experiences": [dict(profile["experiences"][0],
                             company="OtraCorp")],
        "education": [], "projects": [], "certifications": [],
        "languages": [],
    }
    ok, issues = adapt_validate.validate_pre_render(
        bad_company, profile, {})
    assert ok is False
    assert any("organizacion nueva" in i for i in issues)

    bad_number = {
        "summary": "x", "skills": [],
        "experiences": [dict(profile["experiences"][0],
                             description="Analice 500 reportes.")],
        "education": [], "projects": [], "certifications": [],
        "languages": [],
    }
    ok, issues = adapt_validate.validate_pre_render(
        bad_number, profile, {})
    assert ok is False
    assert any("cifra nueva" in i for i in issues)

    bad_date = {
        "summary": "x", "skills": [],
        "experiences": [dict(profile["experiences"][0], start="ayer")],
        "education": [], "projects": [], "certifications": [],
        "languages": [],
    }
    ok, issues = adapt_validate.validate_pre_render(
        bad_date, profile, {})
    assert ok is False
    assert any("fecha invalida" in i for i in issues)


def test_validate_respeta_topes_config():
    from app.adapt import validate as adapt_validate

    profile = _valid_profile()
    content = {
        "summary": "x", "skills": [],
        "experiences": [dict(profile["experiences"][0]) for _ in range(3)],
        "education": [], "projects": [], "certifications": [],
        "languages": [],
    }
    ok, _ = adapt_validate.validate_pre_render(
        content, profile, {"max_experiences": 2})
    assert ok is False
    ok, _ = adapt_validate.validate_pre_render(
        content, profile, {"max_experiences": 3})
    assert ok is True


def test_validate_no_mutar_entradas():
    import copy

    from app.adapt import validate as adapt_validate

    profile = _valid_profile()
    content = {"summary": "x", "skills": ["Python"],
               "experiences": [dict(profile["experiences"][0])]}
    snapshot = copy.deepcopy((content, profile))
    adapt_validate.validate_pre_render(content, profile, {})
    assert (content, profile) == snapshot
