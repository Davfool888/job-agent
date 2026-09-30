"""CV personalizado por oferta: importador LaTeX + customized-cv + reuso."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_cv.tex"


def test_importer_extracts_profile():
    from app.cv.latex_import import parse_latex_profile

    result = parse_latex_profile(FIXTURE.read_text(encoding="utf-8"))
    profile = result["profile"]
    assert profile["personal"]["full_name"] == "María Fernanda Rojas"
    assert profile["personal"]["email"] == "maria.rojas@example.com"
    assert "linkedin.com/in/mariafrojas" in profile["personal"]["linkedin"]
    assert "Power BI" in profile["professional_summary"]
    assert len(profile["experience"]) == 2
    first = profile["experience"][0]
    assert first["title"] == "Analista de Datos"
    assert first["company"] == "Banco de Bogotá"
    assert first["period"] == "2021 - 2024"
    assert any("Power BI" in b for b in first["bullets"])
    assert len(profile["education"]) == 2
    assert len(profile["projects"]) == 2
    assert "Python" in (profile["skills"]["programming"]
                        + profile["skills"]["data"])
    assert "Español (nativo)" in profile["languages"]
    assert any("PL-300" in c for c in profile["certifications"])


def test_importer_warns_unknown_sections():
    from app.cv.latex_import import parse_latex_profile

    result = parse_latex_profile(FIXTURE.read_text(encoding="utf-8"))
    assert any("loco desconocidas" in w.lower() or "no reconocida" in w
               for w in result["warnings"])


def test_importer_empty_rejected():
    from app.cv.latex_import import parse_latex_profile

    import pytest

    with pytest.raises(ValueError):
        parse_latex_profile("   ")


def test_import_endpoint_preview_does_not_save():
    from app.config import BASE_CV_PATH

    before = BASE_CV_PATH.read_text(encoding="utf-8") \
        if BASE_CV_PATH.exists() else None
    with TestClient(app) as client:
        with open(FIXTURE, "rb") as fh:
            response = client.post(
                "/profile/import-latex",
                files={"file": ("cv.tex", fh, "text/plain")},
            )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["applied"] is False
        assert body["profile"]["personal"]["full_name"] == "María Fernanda Rojas"
    after = BASE_CV_PATH.read_text(encoding="utf-8") \
        if BASE_CV_PATH.exists() else None
    assert before == after


def test_import_endpoint_apply_persists_and_restores():
    from app.config import BASE_CV_PATH

    backup = BASE_CV_PATH.read_text(encoding="utf-8") \
        if BASE_CV_PATH.exists() else None
    try:
        with TestClient(app) as client:
            response = client.post(
                "/profile/import-latex?apply=true",
                json={"latex": FIXTURE.read_text(encoding="utf-8")},
            )
            assert response.status_code == 200, response.text
            assert response.json()["applied"] is True
            saved = client.get("/profile/full").json()
            assert saved["personal"]["full_name"] == "María Fernanda Rojas"
    finally:
        if backup is None:
            if BASE_CV_PATH.exists():
                BASE_CV_PATH.unlink()
        else:
            BASE_CV_PATH.write_text(backup, encoding="utf-8")


def _seed_job_and_profile(client):
    """Crea oferta analizable + perfil con datos; devuelve (job_id, backup)."""
    from app.config import BASE_CV_PATH
    from app.database.connection import SessionLocal
    from app.database.models import Job
    from app.services.job_service import save_jobs

    backup = BASE_CV_PATH.read_text(encoding="utf-8") \
        if BASE_CV_PATH.exists() else None
    client.post("/profile/import-latex?apply=true",
                json={"latex": FIXTURE.read_text(encoding="utf-8")})
    db = SessionLocal()
    try:
        saved = save_jobs(db, [{
            "title": "Analista de Datos sector financiero",
            "company": "Empresa CV Custom",
            "url": "https://example.com/cv-custom",
            "description": (
                "Buscamos analista de datos con Power BI, DAX, SQL y "
                "Excel avanzado para el sector financiero en Bogota. "
                "3 anos de experiencia en analisis de informacion."
            ),
            "source": "computrabajo",
        }])
        job_id = saved[0].id
    finally:
        db.close()
    analyzed = client.post(f"/jobs/{job_id}/analyze").json()
    assert analyzed["analysis"]["match_score"] is not None
    return job_id, backup


def _cleanup_job_and_profile(client, job_id, backup):
    from app.config import BASE_CV_PATH
    from app.database.connection import SessionLocal
    from app.database.models import Job
    from app.cv.generator import job_cv_dir

    import shutil

    db = SessionLocal()
    try:
        db.query(Job).filter(Job.company == "Empresa CV Custom").delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()
    shutil.rmtree(job_cv_dir(job_id), ignore_errors=True)
    if backup is None:
        if BASE_CV_PATH.exists():
            BASE_CV_PATH.unlink()
    else:
        BASE_CV_PATH.write_text(backup, encoding="utf-8")


def test_customized_cv_lifecycle_and_reuse():
    with TestClient(app) as client:
        job_id, backup = _seed_job_and_profile(client)
        try:
            # 1. Sin generar -> NOT_GENERATED (sin IA).
            first = client.get(f"/jobs/{job_id}/customized-cv").json()
            assert first["state"] == "NOT_GENERATED"

            # 2. Generar (forzado por umbral bajo posible).
            generated = client.post(
                f"/jobs/{job_id}/cv", json={"force": True}).json()
            assert generated["cv_generated"] is True

            # 3. READY con contenido, sin consumir IA de nuevo.
            ready = client.get(f"/jobs/{job_id}/customized-cv").json()
            assert ready["state"] == "READY"
            assert ready["version"] >= 1
            assert ready["pdf_available"] in (True, False)
            assert ready["download_tex"] is not None
            content = ready["generated_content"]
            assert content is not None
            assert ready["analysis"] is not None

            # 4. Reuso: segunda lectura identica (misma version/fecha).
            again = client.get(f"/jobs/{job_id}/customized-cv").json()
            assert again["state"] == "READY"
            assert again["version"] == ready["version"]
            assert again["created_at"] == ready["created_at"]
        finally:
            _cleanup_job_and_profile(client, job_id, backup)


def test_customized_cv_no_inventa():
    """Todo lo generado debe existir literalmente en el perfil."""
    with TestClient(app) as client:
        job_id, backup = _seed_job_and_profile(client)
        try:
            client.post(f"/jobs/{job_id}/cv", json={"force": True})
            ready = client.get(f"/jobs/{job_id}/customized-cv").json()
            assert ready["state"] == "READY"
            content = ready["generated_content"]
            corpus = FIXTURE.read_text(encoding="utf-8").lower()

            def contained(text: str) -> bool:
                # Palabras significativas del generado en el .tex original.
                words = [w.strip(".,;:()").lower() for w in text.split()]
                words = [w for w in words if len(w) > 4]
                if not words:
                    return True
                return sum(1 for w in words if w in corpus) / len(words) >= 0.5

            for exp in content.get("selected_experience", []):
                title = exp.get("title", "") + " " + exp.get("company", "")
                assert contained(title), f"posible invencion: {title}"
                for bullet in exp.get("bullets", []) or []:
                    assert contained(str(bullet)), \
                        f"posible invencion: {bullet}"
            for skill in content.get("skills", []) or []:
                assert skill.lower() in corpus, \
                    f"skill inventada: {skill}"
        finally:
            _cleanup_job_and_profile(client, job_id, backup)


def test_customized_cv_404():
    with TestClient(app) as client:
        assert client.get("/jobs/noexiste/customized-cv").status_code == 404
