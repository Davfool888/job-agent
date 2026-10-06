"""Aislamiento invitado <-> Google en Adaptar-perfil.

- Sin token -> invitado (demo). Token presente pero invalido -> 401
  (jamas degrada a demo en silencio).
- La descarga sin token solo ve la carpeta guest; con ?token= ve la
  propia. Un usuario autenticado NUNCA recibe el archivo legacy/demo:
  se le regenera el suyo.
- El perfil para CV de un uid Google jamas contiene a 'Andres Felipe'.
"""
import io

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app

UID = "uid-aislamiento"
EMAIL = "aislado@test.test"
COMPANY = "Empresa Aislamiento"


@pytest.fixture()
def _db_job():
    from app.database.connection import SessionLocal
    from app.services.job_service import save_jobs

    db = SessionLocal()
    try:
        saved = save_jobs(db, [{
            "title": "Analista de Datos", "company": COMPANY,
            "url": "https://example.com/aislamiento-1",
            "description": "Python SQL " * 20,
            "source": "computrabajo",
        }], search_query="aislamiento")
        yield saved[0].id
    finally:
        from app.database.models import Job

        db.query(Job).filter(Job.company == COMPANY).delete(
            synchronize_session=False)
        db.commit()
        db.close()


@pytest.fixture()
def _dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ADAPT_CVS_DIR", tmp_path)
    return tmp_path


def _seed_files(base, job_id, owner, legacy=False):
    from app.adapt.service import adapt_dir, legacy_adapt_dir

    if legacy:
        target = legacy_adapt_dir(job_id) / "cv.pdf"
    else:
        target = adapt_dir(job_id, *owner) / "cv.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    tag = owner[0] if owner[0] else "guest"
    target.write_bytes(b"%PDF-1.4 fake-" + tag.encode())
    return target


def test_identidad_sin_token_es_invitado():
    from app.routers.common import _adapt_identity

    assert _adapt_identity(None) == (None, None)

    class _Req:
        headers = {}

    assert _adapt_identity(_Req()) == (None, None)


def test_identidad_token_invalido_no_degrada_a_invitado(monkeypatch):
    import app.auth as auth_module
    from app.routers.common import _adapt_identity

    def _bad(header):
        raise HTTPException(status_code=401, detail="invalido")

    monkeypatch.setattr(auth_module, "verify_bearer_token", _bad)

    class _Req:
        headers = {"authorization": "Bearer falso"}

    with pytest.raises(HTTPException) as exc:
        _adapt_identity(_Req())
    assert exc.value.status_code == 401

    # Sin header pero con ?token= invalido: tambien 401, nunca guest.
    class _Req2:
        headers = {}

    with pytest.raises(HTTPException):
        _adapt_identity(_Req2(), token="falso")


def test_identidad_token_valido_y_503(monkeypatch):
    import app.auth as auth_module
    from app.routers.common import _adapt_identity

    monkeypatch.setattr(auth_module, "verify_bearer_token", lambda h: {
        "uid": UID, "email": EMAIL, "name": "X"})

    class _Req:
        headers = {}

    assert _adapt_identity(_Req(), token="abc") == (UID, EMAIL)

    def _down(header):
        raise HTTPException(status_code=503, detail="sin admin")

    monkeypatch.setattr(auth_module, "verify_bearer_token", _down)

    class _Req3:
        headers = {"authorization": "Bearer x"}

    with pytest.raises(HTTPException) as exc:
        _adapt_identity(_Req3())
    assert exc.value.status_code == 503


def test_download_guest_no_ve_archivo_usuario(_db_job, _dirs, monkeypatch):
    import app.auth as auth_module

    monkeypatch.setattr(auth_module, "verify_bearer_token", lambda h: {
        "uid": UID, "email": EMAIL, "name": "X"})
    _seed_files(_dirs, _db_job, (None, None))
    _seed_files(_dirs, _db_job, (UID, EMAIL))
    with TestClient(app) as client:
        guest = client.get(f"/jobs/{_db_job}/adapt-cv/download",
                           params={"format": "pdf"})
        assert guest.status_code == 200
        assert guest.content == b"%PDF-1.4 fake-guest"
        own = client.get(f"/jobs/{_db_job}/adapt-cv/download",
                         params={"format": "pdf", "token": "abc"})
        assert own.status_code == 200
        assert own.content == b"%PDF-1.4 fake-" + UID.encode()


def test_download_autenticado_no_recibe_legacy(_db_job, _dirs, monkeypatch):
    import app.auth as auth_module

    from app.adapt import service as service_module

    monkeypatch.setattr(auth_module, "verify_bearer_token", lambda h: {
        "uid": UID, "email": EMAIL, "name": "X"})
    _seed_files(_dirs, _db_job, (None, None), legacy=True)

    def _regen(db, job_id, uid, email):
        assert uid == UID  # regenera EL SUYO, no sirve el legacy
        target = service_module.adapt_dir(job_id, uid, email) / "cv.pdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"%PDF-1.4 propio")
        return {"success": True}

    monkeypatch.setattr(service_module, "adapt_profile_for_job", _regen)
    with TestClient(app) as client:
        body = client.get(f"/jobs/{_db_job}/adapt-cv/download",
                          params={"format": "pdf", "token": "abc"})
        assert body.status_code == 200
        assert body.content == b"%PDF-1.4 propio"


def test_perfil_google_jamas_ve_demo():
    from app.database.connection import SessionLocal
    from app.database.models import UserProfile, UserRichProfile
    from app.services.job_service import save_rich_profile_for
    from app.adapt.guest import get_profile_for_cv

    db = SessionLocal()
    try:
        save_rich_profile_for(db, UID, EMAIL, {
            "personal": {"full_name": "Usuario Aislado",
                         "email": EMAIL, "phone": "3000000000"},
            "professional_summary": "Resumen propio.",
            "experience": [{"title": "Analista", "company": "Propia",
                            "description": "Datos propios."}],
        })
        mine = get_profile_for_cv(db, user_id=UID, email=EMAIL)
        blob = str(mine)
        assert mine["full_name"] == "Usuario Aislado"
        assert "Andres Felipe" not in blob
        assert "Andrés Felipe" not in blob
        assert "agronomo" not in blob.lower()

        guest = get_profile_for_cv(db)
        assert "Andres Felipe" in guest["full_name"] or \
            "Andrés Felipe" in guest["full_name"]
    finally:
        db.query(UserProfile).filter(
            UserProfile.uid == UID).delete(synchronize_session=False)
        db.query(UserRichProfile).filter(
            UserRichProfile.uid == UID).delete(synchronize_session=False)
        db.commit()
        db.close()
