"""CVs de referencia por perfil (PDF): subida, validacion, reemplazo,
descarga, borrado y uso como ejemplos en la generacion.
"""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app


def make_pdf(text: str) -> bytes:
    """PDF minimo valido con xref real (pypdf 6.x lo exige)."""
    esc = (text.replace("\\", "\\\\").replace("(", "\\(")
           .replace(")", "\\)"))
    stream = f"BT /F1 12 Tf 50 750 Td ({esc}) Tj ET".encode("latin-1")
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        (b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R"
         b"/Resources<</Font<</F1 5 0 R>>>>>>"),
        b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj".encode() + body + b"endobj\n"
    pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += (f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\n"
            f"startxref\n{pos}\n%%EOF\n").encode()
    return bytes(out)


@pytest.fixture(autouse=True)
def _ensure_tables():
    from app.database.connection import Base, engine

    Base.metadata.create_all(bind=engine)


def _make_profile(name="Perfil CV Test"):
    from app.database.connection import SessionLocal
    from app.services import search_profiles as profiles

    db = SessionLocal()
    try:
        return profiles.create_profile(db, {
            "name": name, "title": "Analista de Datos",
            "sources": ["computrabajo"],
        })
    finally:
        db.close()


def _drop_profile(pid):
    from app.database.connection import SessionLocal
    from app.services import search_profiles as profiles

    db = SessionLocal()
    try:
        profiles.delete_profile(db, pid)
    finally:
        db.close()


def _drop_cv(pid):
    """Limpieza total del CV de un perfil (metadatos + archivos)."""
    from app.database.connection import SessionLocal
    from app.services import profile_cvs as pcvs

    db = SessionLocal()
    try:
        pcvs.delete_profile_cv(db, pid)
    finally:
        db.close()
    try:
        pcvs.cv_dir(pid).rmdir()
    except OSError:
        pass


def test_upload_download_replace_delete():
    pid = None
    try:
        pid = _make_profile()["id"]
        pdf = make_pdf("Analista de datos con Python y SQL")
        with TestClient(app) as client:
            assert client.get(
                f"/search-profiles/{pid}/cv").json()["has_cv"] is False

            up = client.post(
                f"/search-profiles/{pid}/cv",
                files={"file": ("mi_cv.pdf", io.BytesIO(pdf),
                                "application/pdf")},
            )
            assert up.status_code == 201, up.text
            body = up.json()
            assert body["filename"] == "mi_cv.pdf"
            assert body["pages"] == 1
            assert body["chars"] > 0
            assert body["download_url"].endswith("/cv/download")

            got = client.get(f"/search-profiles/{pid}/cv").json()
            assert got["has_cv"] is True

            dl = client.get(f"/search-profiles/{pid}/cv/download")
            assert dl.status_code == 200
            assert dl.content.startswith(b"%PDF-")
            assert "attachment" in dl.headers.get("content-disposition", "")

            # Reemplazo: segundo PDF pisa al primero.
            pdf2 = make_pdf("Segunda version del CV")
            up2 = client.post(
                f"/search-profiles/{pid}/cv",
                files={"file": ("cv2.pdf", io.BytesIO(pdf2),
                                "application/pdf")},
            )
            assert up2.status_code == 201
            assert up2.json()["filename"] == "cv2.pdf"

            assert client.delete(
                f"/search-profiles/{pid}/cv").status_code == 204
            assert client.get(
                f"/search-profiles/{pid}/cv").json()["has_cv"] is False
            assert client.get(
                f"/search-profiles/{pid}/cv/download").status_code == 404
    finally:
        if pid:
            _drop_cv(pid)
            _drop_profile(pid)


def test_rejects_non_pdf_and_missing_profile():
    with TestClient(app) as client:
        assert client.post(
            "/search-profiles/999999/cv",
            files={"file": ("x.pdf", io.BytesIO(make_pdf("t")),
                            "application/pdf")},
        ).status_code == 404
        pid = _make_profile("Perfil CV Rechazo")["id"]
        try:
            bad = client.post(
                f"/search-profiles/{pid}/cv",
                files={"file": ("notas.txt", io.BytesIO(b"hola"),
                                "text/plain")},
            )
            assert bad.status_code == 400
            assert "PDF" in bad.json()["detail"]
        finally:
            _drop_cv(pid)
            _drop_profile(pid)


def test_rejects_oversize(monkeypatch):
    # MAX_CV_BYTES se importa desde app.config dentro de la funcion.
    import app.config as config_module

    monkeypatch.setattr(config_module, "MAX_CV_BYTES", 10)
    pid = _make_profile("Perfil CV Grande")["id"]
    try:
        with TestClient(app) as client:
            big = client.post(
                f"/search-profiles/{pid}/cv",
                files={"file": ("big.pdf",
                                io.BytesIO(make_pdf("texto largo " * 50)),
                                "application/pdf")},
            )
            assert big.status_code == 400
            assert "maximo" in big.json()["detail"].lower()
    finally:
        _drop_cv(pid)
        _drop_profile(pid)


def test_reference_section_and_router_passthrough():
    from app.ai.providers.gemini import _reference_section
    from app.ai.router import AIRouter
    from app.ai.providers.rule_based import RuleBasedProvider

    assert _reference_section(None) == ""
    assert _reference_section([]) == ""
    section = _reference_section([
        {"profile_id": "1", "label": "Datos", "text": "CV ejemplo"},
    ])
    assert "Ejemplo 1 (Datos)" in section
    assert "IGNORA sus datos" in section

    # rule_based ignora ejemplos pero acepta el kwarg (compatibilidad).
    out = AIRouter(providers=[RuleBasedProvider()]).generate_cv_content(
        {"title": "Analista de Datos", "description": "SQL Power BI"},
        {"evidence": ["SQL"]},
        {"skills": ["SQL"]},
        reference_cvs=[{"profile_id": "1", "label": "x", "text": "y"}],
    )
    assert out["provider"] == "rule_based"


def test_references_feed_generation(monkeypatch):
    """El texto del CV del perfil llega al prompt de generacion."""
    from app.services import job_service as jobs

    pid = _make_profile("Perfil CV Ref")["id"]
    try:
        pdf = make_pdf("Formato de CV ejemplo con Power BI")
        with TestClient(app) as client:
            up = client.post(
                f"/search-profiles/{pid}/cv",
                files={"file": ("ref.pdf", io.BytesIO(pdf),
                                "application/pdf")},
            )
            assert up.status_code == 201

            from app.database.connection import SessionLocal

            db = SessionLocal()
            try:
                saved = jobs.save_jobs(db, [{
                    "title": "Analista de Datos",
                    "company": "Empresa Ref",
                    "url": "https://example.com/ref-cv",
                    "description": "SQL Power BI " * 30,
                    "source": "computrabajo",
                }], search_profile_id=str(pid))
                # save_jobs ya devuelve Records frescos.
                job = saved[0]
                from app.services import profile_cvs as pcvs

                refs = pcvs.reference_texts_for_job(db, job)
                assert len(refs) == 1
                assert "Power BI" in refs[0]["text"]
                assert refs[0]["label"] == "Perfil CV Ref"
            finally:
                from app.database.models import Job

                db.query(Job).filter(
                    Job.company == "Empresa Ref").delete(
                        synchronize_session=False)
                db.commit()
                db.close()
    finally:
        _drop_cv(pid)
        _drop_profile(pid)
