"""Perfiles por usuario: solo el admin ve el perfil base global.

- Sin sesion -> perfil global historico (modo local).
- Admin (ADMIN_EMAIL) -> perfil global, puede editarlo.
- Otro usuario -> en blanco hasta que guarda; jamas ve ni toca lo global.
"""
from fastapi.testclient import TestClient

import pytest

from app.main import app


ADMIN = "davfool888@gmail.com"
OTHER = "alguien@example.com"


@pytest.fixture(autouse=True)
def _ensure_tables():
    """Crea las tablas nuevas si no existen (el servidor lo hace en
    lifespan; aqui los tests usan SessionLocal directo)."""
    from app.database.connection import Base, engine

    Base.metadata.create_all(bind=engine)


def _db():
    from app.database.connection import SessionLocal

    return SessionLocal()


def _clean_users():
    db = _db()
    try:
        from app.database.models import UserProfile, UserRichProfile

        db.query(UserProfile).filter(
            UserProfile.uid.in_(["uid-admin-test", "uid-other-test"])
        ).delete(synchronize_session=False)
        db.query(UserRichProfile).filter(
            UserRichProfile.uid.in_(["uid-admin-test", "uid-other-test"])
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_other_user_starts_blank_and_roundtrips():
    from app.services import job_service as jobs

    _clean_users()
    db = _db()
    try:
        # En blanco: ningun campo con contenido.
        blank = jobs.get_profile_for(db, "uid-other-test", OTHER)
        assert blank["scope"] == "own"
        assert blank["full_name"] == ""
        assert blank["skills"] == []

        saved = jobs.save_profile_for(
            db, "uid-other-test", OTHER,
            {"full_name": "Otra Persona", "skills": ["Python"]},
        )
        assert saved["scope"] == "own"
        assert saved["full_name"] == "Otra Persona"

        again = jobs.get_profile_for(db, "uid-other-test", OTHER)
        assert again["full_name"] == "Otra Persona"
        assert again["skills"] == ["Python"]
    finally:
        db.close()
        _clean_users()


def _read_global():
    db = _db()
    try:
        from app.services import job_service as jobs

        return dict(jobs.get_profile(db))
    finally:
        db.close()


def _write_global(data):
    db = _db()
    try:
        from app.services import job_service as jobs

        keep = {k: data.get(k) for k in jobs.DEFAULT_PROFILE}
        jobs.save_profile(db, keep)
    finally:
        db.close()


def test_other_user_never_sees_global():
    from app.services import job_service as jobs

    _clean_users()
    original = _read_global()
    db = _db()
    try:
        # Marca global: el otro usuario no debe verla.
        jobs.save_profile(db, {"full_name": "Perfil Base Global"})
        other = jobs.get_profile_for(db, "uid-other-test", OTHER)
        assert other["full_name"] == ""
        admin = jobs.get_profile_for(db, "uid-admin-test", ADMIN)
        assert admin["scope"] == "admin"
        assert admin["full_name"] == "Perfil Base Global"
        # Sin sesion: comportamiento historico (global).
        shared = jobs.get_profile_for(db, None, None)
        assert shared["scope"] == "shared"
    finally:
        db.close()
        _clean_users()
        _write_global(original)


def test_rich_profile_isolated_and_file_untouched():
    import json

    from app.config import BASE_CV_PATH
    from app.services import job_service as jobs

    _clean_users()
    before = BASE_CV_PATH.read_text(encoding="utf-8") \
        if BASE_CV_PATH.exists() else None
    db = _db()
    try:
        blank = jobs.get_rich_profile_for(db, "uid-other-test", OTHER)
        assert blank["scope"] == "own"
        assert blank["experience"] == []

        out = jobs.save_rich_profile_for(
            db, "uid-other-test", OTHER,
            {"personal": {"full_name": "Otra Persona"}, "experience": []},
        )
        assert out["scope"] == "own"
        again = jobs.get_rich_profile_for(db, "uid-other-test", OTHER)
        assert again["personal"].get("full_name") == "Otra Persona"

        after = BASE_CV_PATH.read_text(encoding="utf-8") \
            if BASE_CV_PATH.exists() else None
        assert after == before  # base_cv.json intacto
    finally:
        db.close()
        _clean_users()


def test_endpoints_route_by_session(monkeypatch):
    """GET/PUT /profile con sesion no-admin no tocan el global."""
    import app.auth as auth_module

    def fake_verify(authorization):
        assert authorization == "Bearer x"
        return {"uid": "uid-other-test", "email": OTHER, "name": "Otra"}

    # _profile_identity hace `from app.auth import verify_bearer_token`
    # en cada llamada: parchar el atributo del modulo funciona.
    monkeypatch.setattr(auth_module, "verify_bearer_token", fake_verify)
    _clean_users()
    original = _read_global()
    with TestClient(app) as client:
        body = client.get(
            "/profile", headers={"Authorization": "Bearer x"}).json()
        assert body["scope"] == "own"
        assert body["full_name"] == ""
        saved = client.put(
            "/profile", json={"full_name": "Otra Persona"},
            headers={"Authorization": "Bearer x"}).json()
        assert saved["scope"] == "own"
        assert saved["full_name"] == "Otra Persona"
        # El global sigue intacto.
        assert _read_global()["full_name"] == original.get("full_name")
    _clean_users()
    _write_global(original)
