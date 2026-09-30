"""Pruebas contra Cloud Firestore REAL (proyecto job-agent-davfo).

Se omiten si no hay credenciales (GOOGLE_APPLICATION_CREDENTIALS o
emulador). Todo lo creado lleva prefijo tst- y se borra al final.
NO tocan datos reales: los ids de prueba usan urls example.com.
"""
import os

import pytest

from app.database.firestore_client import FirestoreDatabase

CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
EMULATOR = os.getenv("FIRESTORE_EMULATOR_HOST", "")

needs_firestore = pytest.mark.skipif(
    not (CREDENTIALS or EMULATOR),
    reason="sin credenciales Firestore (GOOGLE_APPLICATION_CREDENTIALS)",
)

TEST_URLS = [
    "https://example.com/fstest-1",
    "https://example.com/fstest-2",
]


@pytest.fixture()
def fsdb():
    from app.services import job_service as jobs

    db = FirestoreDatabase()
    yield db
    # Limpieza: borra todo lo creado por estos tests.
    for url in TEST_URLS:
        existing = jobs.get_job_by_url(db, url)
        if existing:
            jobs.delete_job(db, existing.id)


def _offer(url: str, title: str = "Oferta Firestore Test",
           company: str = "Empresa FSTest") -> dict:
    return {
        "title": title,
        "company": company,
        "location": "Bogota",
        "url": url,
        "description": ("Analista de datos con Power BI y SQL. " * 20).strip(),
        "source": "computrabajo",
    }


@needs_firestore
def test_crud_y_dedup(fsdb):
    from app.services import job_service as jobs

    saved = jobs.save_jobs(fsdb, [_offer(TEST_URLS[0])], search_query="t")
    assert len(saved) == 1
    job_id = saved[0].id
    assert isinstance(job_id, str) and job_id.strip() != ""

    # Segunda guardada misma URL -> sin duplicado.
    again = jobs.save_jobs(fsdb, [_offer(TEST_URLS[0])], search_query="t2")
    assert again[0].id == job_id

    fetched = jobs.get_job_by_id(fsdb, job_id)
    assert fetched is not None and fetched.title == "Oferta Firestore Test"

    updated = jobs.update_job_fields(fsdb, job_id, {"location": "Medellin"})
    assert updated.location == "Medellin"
    assert jobs.refresh_job(fsdb, updated).location == "Medellin"

    listed = jobs.get_all_jobs(fsdb, limit=500)
    assert any(j.id == job_id for j in listed)


@needs_firestore
def test_status_y_analisis(fsdb):
    from app.services import job_service as jobs

    saved = jobs.save_jobs(fsdb, [_offer(TEST_URLS[1])], search_query="t")
    job = saved[0]

    kept = jobs.update_job_status(fsdb, job, "kept")
    assert kept.status == "kept"

    analyzed = jobs.save_analysis(
        fsdb, kept, match_score=82.5, matched=["Power BI"],
        missing=["AWS"], detected_role="Data Analyst",
        category="DATA_ANALYST", evidence=["Power BI"],
        experience="2 año(s) de experiencia",
    )
    assert analyzed.match_score == 82.5
    assert analyzed.detected_role == "Data Analyst"
    assert analyzed.matched_skills == ["Power BI"]

    discarded = jobs.update_job_status(
        fsdb, analyzed, "discarded", discard_reason="Salario",
        discard_note="muy bajo",
    )
    assert discarded.status == "discarded"
    # Nunca se elimina: el documento sigue existiendo.
    assert jobs.get_job_by_id(fsdb, job.id) is not None


@needs_firestore
def test_profile_applications_cvs_interactions(fsdb):
    from app.services import job_service as jobs

    profile = jobs.get_profile(fsdb)
    assert "skills" in profile and "target_roles" in profile
    saved = jobs.save_profile(
        fsdb, {**profile, "skills": ["Python"], "target_roles": ["Data Analyst"]}
    )
    assert saved["skills"] == ["Python"]

    applied = jobs.update_job_status(
        fsdb, jobs.save_jobs(fsdb, [_offer(TEST_URLS[0])])[0], "applied",
        application_status="entrevista",
    )
    apps = jobs.list_applications(fsdb)
    mine = [a for a in apps if a["job_id"] == applied.id]
    assert len(mine) == 1
    assert mine[0]["status"] == "INTERVIEW"
    assert len(mine[0]["events"]) >= 2  # creada + cambio de etapa

    cv = jobs.register_cv_version(fsdb, applied.id, {
        "tex_path": "/tmp/x.tex", "match_score": 80.0,
        "skills_selected": ["Python"],
    })
    assert cv["version"] >= 1 and cv["status"] == "GENERATED"

    iid = jobs.log_interaction(fsdb, "JOB_VIEWED", applied.id)
    assert iid

    stats = jobs.get_stats(fsdb)
    assert stats["total"] >= 1
    assert "by_status" in stats and "top_skills" in stats


@needs_firestore
def test_api_sobre_firestore(fsdb, monkeypatch):
    """Humo end-to-end: la API responde con el motor Firestore."""
    import app.config as config
    from app.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(config, "DB_BACKEND", "firestore")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        body = client.get("/jobs", params={"limit": 5}).json()
        assert isinstance(body, list)
        stats = client.get("/stats").json()
        assert "total" in stats
        apps = client.get("/applications").json()
        assert isinstance(apps, list)
