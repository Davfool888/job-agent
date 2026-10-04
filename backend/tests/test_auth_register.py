"""Registro/login estrictos: sin registro no hay entrada, y el
telefono se pide una sola vez."""
from fastapi.testclient import TestClient

import app.auth as auth_module
from app.main import app

UID, EMAIL, NAME, PHONE = (
    "uid-reg-1", "reg1@example.com", "Reg Uno", "+57 300 111 2222")


def _fake(uid=UID, email=EMAIL, name=NAME):
    def verify(authorization):
        assert authorization == "Bearer x"
        return {"uid": uid, "email": email, "name": name}
    return verify


def _clean():
    from app.database.connection import SessionLocal
    from app.database.models import User

    db = SessionLocal()
    try:
        db.query(User).filter(User.uid == UID).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_register_then_login(monkeypatch):
    monkeypatch.setattr(auth_module, "verify_bearer_token", _fake())
    _clean()
    try:
        with TestClient(app) as client:
            # Login sin registro -> 404, no crea nada reutilizable
            r = client.post("/auth/login",
                            headers={"Authorization": "Bearer x"})
            assert r.status_code == 404, r.text
            assert r.json()["code"] == "NOT_REGISTERED"

            # Registro -> 201 con telefono guardado
            r = client.post(
                "/auth/register",
                json={"nombre": NAME, "telefono": PHONE},
                headers={"Authorization": "Bearer x"})
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["telefono"] == PHONE
            assert body["is_profile_complete"] is True

            # Re-registro -> 409, no pisa
            r = client.post(
                "/auth/register",
                json={"nombre": "Otro", "telefono": "+57 999"},
                headers={"Authorization": "Bearer x"})
            assert r.status_code == 409, r.text
            assert r.json()["code"] == "ACCOUNT_EXISTS"

            # Login ahora si entra, sin pedir nada mas
            r = client.post("/auth/login",
                            headers={"Authorization": "Bearer x"})
            assert r.status_code == 200, r.text
            assert r.json()["telefono"] == PHONE

            # GET /auth/me tambien lo ve completo (compatibilidad)
            me = client.get("/auth/me",
                            headers={"Authorization": "Bearer x"}).json()
            assert me["is_profile_complete"] is True
            assert me["telefono"] == PHONE
    finally:
        _clean()


def test_register_requires_phone(monkeypatch):
    monkeypatch.setattr(auth_module, "verify_bearer_token", _fake())
    _clean()
    try:
        with TestClient(app) as client:
            r = client.post(
                "/auth/register", json={"nombre": NAME, "telefono": "  "},
                headers={"Authorization": "Bearer x"})
            assert r.status_code == 400, r.text
            # No quedo registro a medias: login sigue 404
            r = client.post("/auth/login",
                            headers={"Authorization": "Bearer x"})
            assert r.status_code == 404
    finally:
        _clean()


def test_anonymous_cannot_register(monkeypatch):
    monkeypatch.setattr(
        auth_module, "verify_bearer_token",
        _fake(uid="anon-x", email="", name=""))
    with TestClient(app) as client:
        r = client.post(
            "/auth/register", json={"nombre": "X", "telefono": "123"},
            headers={"Authorization": "Bearer x"})
        assert r.status_code == 400, r.text
