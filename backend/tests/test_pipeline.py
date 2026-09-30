"""Pipeline §14-§16, matching §6, CV §10-§13, router §8."""
import json

from fastapi.testclient import TestClient

from app.ai.router import AIRouter
from app.ai.schemas.cv_content import CVContent
from app.ai.schemas.job_analysis import JobAnalysisResult
from app.cv import generator as cvgen
from app.main import app
from app.scraper.normalize import content_hash_of
from app.scraper.normalize import normalize_job
from app.services import matching_service


def test_normalize_defaults():
    job = normalize_job({"title": "T", "url": "https://x/y"})
    assert job["source"] == "computrabajo"
    assert job["external_id"] is None
    assert job["requirements"] == []
    assert job["responsibilities"] == []
    assert job["salary"] == ""
    assert job["tags"] == [] if "tags" in job else True


def test_dedup_external_id_first():
    from app.database.connection import SessionLocal
    from app.database.models import Job
    from app.services.job_service import save_jobs

    db = SessionLocal()
    try:
        first = save_jobs(db, [{
            "title": "Oferta Dedup EXT",
            "company": "Empresa Dedup",
            "url": "https://example.com/dedup-a",
            "description": "x" * 300,
            "source": "linkedin",
            "external_id": "999",
        }])
        second = save_jobs(db, [{
            "title": "Oferta Dedup EXT",
            "company": "Empresa Dedup",
            "url": "https://example.com/dedup-b-distinta",
            "description": "x" * 300,
            "source": "linkedin",
            "external_id": "999",
        }])
        assert first[0].id == second[0].id
    finally:
        db.query(Job).filter(Job.company == "Empresa Dedup").delete(
            synchronize_session=False)
        db.commit()
        db.close()


def test_dedup_content_hash():
    from app.database.connection import SessionLocal
    from app.database.models import Job
    from app.services.job_service import save_jobs

    long_desc = "Descripcion larga repetida. " * 30
    assert content_hash_of(long_desc) is not None
    assert content_hash_of("corta") is None
    db = SessionLocal()
    try:
        first = save_jobs(db, [{
            "title": "Oferta Hash Uno",
            "company": "Empresa Hash",
            "url": "https://example.com/hash-1",
            "description": long_desc,
            "source": "magneto",
        }])
        second = save_jobs(db, [{
            "title": "Oferta Hash Uno editada",
            "company": "Empresa Hash",
            "url": "https://example.com/hash-2",
            "description": long_desc,
            "source": "magneto",
        }])
        # Mismo contenido -> se fusiona en la primera fila.
        assert first[0].id == second[0].id
    finally:
        db.query(Job).filter(Job.company == "Empresa Hash").delete(
            synchronize_session=False)
        db.commit()
        db.close()


def test_matching_weights_configurable():
    assert sum(matching_service.MATCH_WEIGHTS.values()) == 100
    out = matching_service.combine(
        {"title": 20, "skills": 30, "responsibilities": 30, "tools": 20},
        "DATA_ANALYST",
        {"skills": [], "target_roles": []},
        "analista de datos sql python",
    )
    assert out["match_score"] == 100
    assert out["goal_bonus"] == 0
    out2 = matching_service.combine(
        {"title": 0, "skills": 0, "responsibilities": 0, "tools": 0},
        "OTHER",
        {"skills": ["SQL"], "target_roles": []},
        "vendedor",
    )
    assert out2["match_score"] == 0
    assert out2["missing_skills"] == ["SQL"]


def test_cv_selection_no_inventa():
    from app.agents.cv_agent import CVAgent

    profile = {
        "personal": {"full_name": "Ana Prueba"},
        "professional_summary": "Analista con 2 años.",
        "experience": [
            {"title": "Analista de datos", "company": "Banco X",
             "period": "2023-2024",
             "bullets": ["Dashboards en Power BI"]},
            {"title": "Vendedora", "company": "Tienda Y",
             "period": "2021",
             "bullets": ["Atencion al cliente"]},
        ],
        "projects": [],
        "skills": {"data": ["Power BI", "SQL"], "tools": ["Excel"]},
        "education": [],
    }
    content = CVAgent().select_content(
        {"title": "Analista de Datos",
         "description": "Power BI dashboards SQL"},
        {"evidence": ["Power BI", "SQL"]},
        profile,
    )
    assert isinstance(content, CVContent)
    # Lo relevante primero, sin inventar empresas ni skills.
    assert content.selected_experience[0]["company"] == "Banco X"
    assert "SAP" not in content.skills
    assert set(content.skills) <= {"Power BI", "SQL", "Excel"}


def test_tex_escape():
    tex = cvgen.render_tex(
        CVContent(professional_summary="100% & listo_"),
        {"full_name": "A&B", "title": "", "email": "a@b.co"},
    )
    assert "A\\&B" in tex
    assert "100\\% \\& listo\\_" in tex
    assert "{{FULL_NAME}}" not in tex


def test_router_fallback_chain():
    from app.ai.providers.base import AIProvider

    class Falla(AIProvider):
        name = "falla"

        def available(self):
            return True

        def analyze_job(self, job, profile):
            raise TimeoutError("timeout simulado")

        def generate_cv_content(self, job, analysis, profile):
            raise RuntimeError("caido")

    router = AIRouter(providers=[Falla(), __import__(
        "app.ai.providers.rule_based",
        fromlist=["RuleBasedProvider"]).RuleBasedProvider()])
    out = router.analyze_job({"title": "Analista de Datos",
                              "description": "SQL Power BI"},
                             {"skills": ["SQL"]})
    assert out["provider"] == "rule_based"
    assert out["category"] == "DATA_ANALYST"


def test_router_status_endpoint():
    with TestClient(app) as client:
        body = client.get("/ai/status").json()
        assert "providers" in body
        names = [p["provider"] for p in body["providers"]]
        assert "rule_based" in names
        rb = [p for p in body["providers"] if p["provider"] == "rule_based"][0]
        assert rb["available"] is True


def test_cv_threshold_endpoints():
    from app.config import BASE_CV_PATH

    backup = BASE_CV_PATH.read_text(encoding="utf-8") \
        if BASE_CV_PATH.exists() else None
    # Perfil vacio para este test (el entorno puede tener perfil real).
    BASE_CV_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASE_CV_PATH.write_text(
        '{"personal": {}, "skills": {}, "experience": [], '
        '"projects": [], "education": []}',
        encoding="utf-8",
    )
    with TestClient(app) as client:
        from app.database.connection import SessionLocal
        from app.database.models import Job
        from app.services.job_service import save_jobs

        db = SessionLocal()
        try:
            saved = save_jobs(db, [{
                "title": "Oferta CV Umbral",
                "company": "Empresa CV",
                "url": "https://example.com/cv-umbral",
                "description": "SQL",
                "source": "computrabajo",
            }])
            job_id = saved[0].id
        finally:
            db.close()

        try:
            # Sin analisis -> 400 honesto.
            response = client.post(f"/jobs/{job_id}/cv", json={})
            assert response.status_code == 400

            analyzed = client.post(f"/jobs/{job_id}/analyze").json()
            score = analyzed["analysis"]["match_score"]
            assert score < 50  # descripcion pobre

            # Score bajo sin force -> no genera.
            denied = client.post(f"/jobs/{job_id}/cv", json={}).json()
            assert denied["decision"] == "below_threshold"
            assert denied["cv_generated"] is False

            # Score bajo con force pero perfil vacio -> 400 (no inventa).
            forced = client.post(f"/jobs/{job_id}/cv",
                                 json={"force": True})
            assert forced.status_code == 400
        finally:
            db = SessionLocal()
            db.query(Job).filter(Job.company == "Empresa CV").delete(
                synchronize_session=False)
            db.commit()
            db.close()
            if backup is None:
                if BASE_CV_PATH.exists():
                    BASE_CV_PATH.unlink()
            else:
                BASE_CV_PATH.write_text(backup, encoding="utf-8")


def test_analysis_json_schema():
    parsed = JobAnalysisResult.model_validate({
        "category": "DATA_ANALYST", "match_score": 87,
        "evidence": ["Power BI"], "matching_skills": ["Power BI"],
        "missing_skills": ["SQL"]})
    assert parsed.match_score == 87
    import pydantic

    try:
        JobAnalysisResult.model_validate({"match_score": 150})
        valid = True
    except pydantic.ValidationError:
        valid = False
    assert valid is False
    assert json.loads('{"a": 1}')["a"] == 1
