"""Adaptar-perfil: matching, seleccion, HTML, PDF y endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.adapt import guest, html_renderer, llm, matcher, selector
from app.adapt.test_jobs import ensure_adapt_test_jobs
from app.main import app


@pytest.fixture(autouse=True)
def _ensure_tables():
    from app.database.connection import Base, engine

    Base.metadata.create_all(bind=engine)


def _db():
    from app.database.connection import SessionLocal

    return SessionLocal()


def _guest_profile():
    return guest.get_profile_for_cv(_db())


def test_guest_profile_shape():
    profile = _guest_profile()
    # full_name deriva de first + last del estructurado.
    assert profile["full_name"] == "Andrés Felipe Ramírez Torres"
    assert "Python" in profile["skills_technical"]
    assert len(profile["experience"]) == 2
    assert len(profile["projects"]) == 2
    assert len(profile["certifications"]) == 2
    assert len(profile["languages"]) == 2


def test_matcher_offer_a_data_role():
    from app.adapt.test_jobs import TEST_JOBS

    offer = dict(TEST_JOBS[0])
    result = matcher.match_offer_profile(offer, _guest_profile())
    assert result["percentage"] >= 60
    for skill in ("Python", "SQL", "Power BI", "Excel"):
        assert skill in result["matched_skills"]
    top_exp = result["experiences"][0]["item"]
    assert top_exp["company"] == "FinanRed S.A.S."


def test_matcher_offer_b_backend_role():
    from app.adapt.test_jobs import TEST_JOBS

    offer = dict(TEST_JOBS[1])
    result = matcher.match_offer_profile(offer, _guest_profile())
    assert "Python" in result["matched_skills"]
    assert "FastAPI" in result["matched_skills"]
    top_exp = result["experiences"][0]["item"]
    assert top_exp["company"] == "TechNova Solutions"


def test_matcher_offer_c_prioritizes_retail_project():
    from app.adapt.test_jobs import TEST_JOBS

    offer = dict(TEST_JOBS[2])
    result = matcher.match_offer_profile(offer, _guest_profile())
    assert "Power BI" in result["matched_skills"]
    top_proj = result["projects"][0]["item"]
    assert top_proj["name"] == "Retail Intelligence Dashboard"


def test_selector_compact_and_coherent():
    from app.adapt.test_jobs import TEST_JOBS

    offer = dict(TEST_JOBS[0])
    profile = _guest_profile()
    matching = matcher.match_offer_profile(offer, profile)
    content = selector.select_cv_content(profile, offer, matching)
    assert content["company"] == "DataCorp Colombia"
    assert len(content["experiences"]) <= 3
    assert len(content["skills"]) <= 12
    assert "Python" in content["skills"]
    assert content["experiences"][0]["company"] == "FinanRed S.A.S."


def test_llm_off_by_default():
    assert llm.llm_available() is False
    out = llm.polish_summary("Resumen original", "Analista", ["Python"])
    assert out == {"summary": "Resumen original", "provider": "none"}


def test_html_escapes_and_renders():
    profile = _guest_profile()
    profile["full_name"] = "<script>alert(1)</script>"
    content = {
        "full_name": profile["full_name"],
        "target_role": "Analista",
        "company": "DataCorp",
        "summary": "Resumen.",
        "skills": ["Python"],
        "experiences": [],
        "education": [],
        "projects": [],
        "certifications": [],
        "languages": [],
    }
    html_text = html_renderer.render_cv_html(
        content, {"title": "Analista", "company": "DataCorp"})
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text
    assert "Analista" in html_text


def test_pdf_generates_valid_file(tmp_path):
    from app.adapt import pdf as pdf_module

    out = tmp_path / "cv.pdf"
    pdf_module.html_to_pdf("<h1>Hola CV</h1>", out, timeout_ms=30000)
    assert out.stat().st_size > 0
    with open(out, "rb") as handler:
        assert handler.read(5) == b"%PDF-"


def test_pdf_rejects_empty_html(tmp_path):
    from app.adapt import pdf as pdf_module

    with pytest.raises(pdf_module.PdfError) as exc:
        pdf_module.html_to_pdf("   ", tmp_path / "cv.pdf")
    assert exc.value.code == "PDF_EMPTY_HTML"


def test_pdf_missing_browser_triggers_install(monkeypatch, tmp_path):
    """Sin Chromium: BROWSER_MISSING + instalacion en fondo (una vez)."""
    from app.adapt import pdf as pdf_module

    calls: list = []

    class FakeBrowser:
        def close(self):
            pass

    class FakeChromium:
        def launch(self, **kwargs):
            raise RuntimeError(
                "BrowserType.launch: Executable doesn't exist at /x")

    class FakeRunner:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    import playwright.sync_api as pw_sync

    monkeypatch.setattr(pw_sync, "sync_playwright",
                        lambda: FakeRunner())
    monkeypatch.setattr(
        pdf_module.subprocess, "run",
        lambda *a, **k: calls.append(a) or __import__(
            "subprocess").CompletedProcess(a, 0))
    with pytest.raises(pdf_module.PdfError) as exc:
        pdf_module.html_to_pdf("<h1>x</h1>", tmp_path / "cv.pdf")
    assert exc.value.code == "BROWSER_MISSING"
    import time

    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        time.sleep(0.05)
    assert calls, "debió disparar la instalación en fondo"
    assert "install" in " ".join(map(str, calls[0]))


def test_endpoint_adapt_flow():
    from app.database.models import Job

    db = _db()
    try:
        saved = ensure_adapt_test_jobs(db)
        by_key = {}
        from app.adapt.test_jobs import TEST_JOBS

        for row, spec in zip(saved, TEST_JOBS):
            by_key[spec["key"]] = row.id
    finally:
        db.close()
    try:
        with TestClient(app) as client:
            body = client.post(
                f"/jobs/{by_key['A']}/adapt-cv").json()
            assert body["success"] is True
            assert body["matching"]["percentage"] >= 60
            assert body["job"]["company"] == "DataCorp Colombia"
            assert body["cv"]["download_url"].endswith(
                "/adapt-cv/download?format=pdf")
            assert body["cv"]["projects"]

            dl = client.get(
                f"/jobs/{by_key['A']}/adapt-cv/download",
                params={"format": "pdf"})
            assert dl.status_code == 200
            assert dl.content.startswith(b"%PDF-")

            missing = client.post("/jobs/999999/adapt-cv").json()
            assert missing["success"] is False
            assert missing["error"]["code"] == "JOB_NOT_FOUND"

            no_cv = client.get("/jobs/999999/adapt-cv/download")
            assert no_cv.status_code == 404
    finally:
        db = _db()
        db.query(Job).filter(
            Job.url.like("https://example.com/adapt-test-%")).delete(
                synchronize_session=False)
        db.commit()
        db.close()
        import shutil

        from app.config import ADAPT_CVS_DIR

        if ADAPT_CVS_DIR.exists():
            for child in ADAPT_CVS_DIR.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)


def test_seed_offers_idempotent():
    db = _db()
    try:
        first = ensure_adapt_test_jobs(db)
        second = ensure_adapt_test_jobs(db)
        assert [j.id for j in first] == [j.id for j in second]
    finally:
        from app.database.models import Job

        db.query(Job).filter(
            Job.url.like("https://example.com/adapt-test-%")).delete(
                synchronize_session=False)
        db.commit()
        db.close()


def test_download_regenerates_missing_pdf():
    """Disco efimero: si el PDF se pierde pero la oferta existe, la
    descarga lo regenera en vez de 404."""
    from app.database.models import Job

    db = _db()
    try:
        saved = ensure_adapt_test_jobs(db)
        job_id = saved[0].id
    finally:
        db.close()
    try:
        with TestClient(app) as client:
            assert client.post(f"/jobs/{job_id}/adapt-cv").status_code == 200
            from app.adapt.service import adapt_dir

            pdf = adapt_dir(job_id) / "cv.pdf"
            assert pdf.exists()
            pdf.unlink()  # simula reinicio con disco efimero
            dl = client.get(f"/jobs/{job_id}/adapt-cv/download",
                            params={"format": "pdf"})
            assert dl.status_code == 200, dl.text[:200]
            assert dl.content.startswith(b"%PDF-")
            assert pdf.exists()  # regenerado en disco
    finally:
        db = _db()
        db.query(Job).filter(
            Job.url.like("https://example.com/adapt-test-%")).delete(
                synchronize_session=False)
        db.commit()
        db.close()
        import shutil

        from app.config import ADAPT_CVS_DIR

        if ADAPT_CVS_DIR.exists():
            for child in ADAPT_CVS_DIR.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
