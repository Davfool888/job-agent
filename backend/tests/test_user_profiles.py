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


def _clean_guest_demo():
    """Borra el demo sembrado para forzar re-siembra con datos nuevos."""
    from app.services.search_profiles import GUEST_OWNER

    db = _db()
    try:
        from app.database.models import UserProfile, UserRichProfile

        db.query(UserProfile).filter(
            UserProfile.uid == GUEST_OWNER).delete(
                synchronize_session=False)
        db.query(UserRichProfile).filter(
            UserRichProfile.uid == GUEST_OWNER).delete(
                synchronize_session=False)
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


GUEST_UID = "anon-test-uid"
GUEST_EMAIL = ""  # anonimo: sin email
OTHER2 = "tercero@example.com"


def _clean_search_tests():
    from app.database.connection import SessionLocal
    from app.database.models import SearchProfile

    db = SessionLocal()
    try:
        db.query(SearchProfile).filter(
            SearchProfile.name.like("SP-Test-%")).delete(
                synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_guest_gets_demo_profile_not_global():
    from app.services import job_service as jobs

    _clean_guest_demo()
    original = _read_global()
    db = _db()
    try:
        jobs.save_profile(db, {"full_name": "Perfil Base Global"})
        guest = jobs.get_profile_for(db, GUEST_UID, GUEST_EMAIL)
        assert guest["scope"] == "demo"
        assert guest["full_name"] == "Andrés Felipe Ramírez"
        assert guest["title"] == "Ingeniero Agrónomo"
        assert "QGIS" in guest["skills"]
        assert "Agroindustria" in guest["sectors"]
        assert guest["min_salary"] == "3200000"
        # El otro Google sigue en blanco.
        other = jobs.get_profile_for(db, "uid-other-test", OTHER)
        assert other["scope"] == "own"
        assert other["full_name"] == ""
    finally:
        db.close()
        _write_global(original)


def test_guest_demo_rich_seeded():
    from app.services import job_service as jobs

    _clean_guest_demo()
    db = _db()
    try:
        rich = jobs.get_rich_profile_for(db, GUEST_UID, GUEST_EMAIL)
        assert rich["scope"] == "demo"
        # full_name se deriva de first + last ("... Torres").
        assert rich["personal"].get("first_name") == "Andrés Felipe"
        assert rich["personal"].get("last_name") == "Ramírez Torres"
        assert rich["personal"].get("full_name") == (
            "Andrés Felipe Ramírez Torres")
        assert rich["personal"].get("email") == (
            "andres.ramirez.agro@example.com")
        assert rich["personal"].get("title_id") == "agronomist"
        assert "palma" in rich["professional_summary"].lower()
        assert rich["years_experience"] == 2
        assert len(rich["technical_skills"]) == 14
        assert len(rich["soft_skills"]) == 8
        for skill in ("Manejo integrado de plagas (MIP)",
                      "QGIS", "Riego y drenaje"):
            assert skill in rich["technical_skills"]
        for skill in ("Trabajo en campo", "Comunicación con productores",
                      "Organización"):
            assert skill in rich["soft_skills"]
        assert len(rich["target_roles"]) == 4
        assert set(rich["skills"]) >= {
            "analysis", "languages", "bi", "databases", "automation",
            "backend", "ml", "tools"}
        assert len(rich["languages"]) == 2
        assert rich["languages"][0]["language"] == "en"
        assert rich["languages"][1]["level"] == "A2"
        assert len(rich["experience"]) == 2
        assert len(rich["education"]) == 2
        assert len(rich["projects"]) == 2
        assert len(rich["certifications"]) == 2
        exp1 = rich["experience"][0]
        assert exp1["company"] == "Palmas del Llano S.A.S."
        assert exp1["start_date"] == "2024-03-01"
        assert exp1["end_date"] == "2025-12-01"
        assert exp1["modality"] == "ONSITE"
        assert exp1["city"]["id"] == "villavicencio"
        assert exp1["contract_type"] is None  # el fixture no lo trae
        assert exp1["technical_skills"][:3] == [
            "Manejo integrado de plagas (MIP)", "Fertilidad de suelos",
            "Nutrición vegetal"]
        assert rich["certifications"][0]["issued_date"] == "2025-05-15"
        assert rich["certifications"][1]["expiry_date"] is None
        # Datos limpios y en catalogo: sin advertencias de validacion.
        assert rich["_warnings"] == []
    finally:
        db.close()


def test_search_profiles_scoping():
    from app.services import search_profiles as profiles

    _clean_search_tests()
    created = []
    db = _db()
    try:
        mine = profiles.create_profile_for(
            db, {"title": "SP-Test-Analista", "name": "SP-Test-Mio"},
            "uid-other-test", OTHER)
        created.append(mine["id"])
        assert mine["owner_uid"] == "uid-other-test"

        # Invitado: solo demos (sembra 2).
        guest_list = profiles.list_profiles_for(db, GUEST_UID, GUEST_EMAIL)
        assert len(guest_list) >= 2
        assert all(p.get("is_demo") for p in guest_list)
        assert all("Demo" in (p.get("name") or "") for p in guest_list)
        assert mine["id"] not in {p["id"] for p in guest_list}

        # Otro Google: solo lo suyo (sin demos, sin lo ajeno).
        other_list = profiles.list_profiles_for(
            db, "uid-other-test", OTHER)
        assert {p["id"] for p in other_list} == {mine["id"]}

        # Tercero: no ve lo ajeno.
        assert profiles.get_profile_for(
            db, mine["id"], "uid-third-test", OTHER2) is None

        # Invitado no toca lo ajeno.
        assert profiles.update_profile_for(
            db, mine["id"], {"title": "X"}, GUEST_UID, GUEST_EMAIL) is None
        assert profiles.delete_profile_for(
            db, mine["id"], GUEST_UID, GUEST_EMAIL) is False
    finally:
        db.close()
        _clean_search_tests()


def test_bad_token_is_401_not_global(monkeypatch):
    """Token presente pero invalido -> 401, jamas el global."""
    import app.auth as auth_module
    from fastapi import HTTPException

    def fake_verify(authorization):
        raise HTTPException(status_code=401, detail="Sesion invalida.")

    monkeypatch.setattr(auth_module, "verify_bearer_token", fake_verify)
    with TestClient(app) as client:
        assert client.get(
            "/profile", headers={"Authorization": "Bearer malo"}
        ).status_code == 401
        assert client.get(
            "/search-profiles", headers={"Authorization": "Bearer malo"}
        ).status_code == 401
