"""Telegram fase 1: vinculacion, notificaciones y errores.

Todo con HTTP simulado (sin red real) y SQLite local.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

UID = "uid-tg-test"
EMAIL = "tg@test.test"
UID2 = "uid-tg-test-2"
COMPANY = "Empresa Telegram Test"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture()
def _env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TESTTOKEN123")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "test_job_bot")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "testsecret")
    monkeypatch.delenv("TELEGRAM_PUBLIC_URL", raising=False)
    yield
    from app.database.connection import SessionLocal
    from app.database.models import TelegramLink, TelegramSent

    db = SessionLocal()
    try:
        for uid in (UID, UID2):
            db.query(TelegramLink).filter(
                TelegramLink.uid == uid).delete(
                    synchronize_session=False)
            db.query(TelegramSent).filter(
                TelegramSent.uid == uid).delete(
                    synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def _auth(monkeypatch):
    import app.auth as auth_module

    orig = auth_module.verify_bearer_token

    def fake(authorization, uid=UID, email=EMAIL):
        assert (authorization or "").startswith("Bearer ")
        return {"uid": uid, "email": email, "name": "T"}

    monkeypatch.setattr(auth_module, "verify_bearer_token", fake)
    return orig


def _ok_sender(monkeypatch, message_id=77):
    import httpx

    def fake_post(url, json=None, timeout=None):
        return FakeResponse(200, {"ok": True,
                                  "result": {"message_id": message_id}})

    monkeypatch.setattr(httpx, "post", fake_post)


def _make_job(company=COMPANY, url="https://example.com/tg-1"):
    from app.database.connection import SessionLocal
    from app.services.job_service import save_jobs

    db = SessionLocal()
    try:
        saved = save_jobs(db, [{
            "title": "Analista Telegram", "company": company, "url": url,
            "location": "Bogota", "modality": "Remoto",
            "salary": "$3.000.000", "description": "Python datos " * 30,
            "source": "computrabajo",
        }], search_query="tg")
        return saved[0].id
    finally:
        db.close()


def _clean_jobs():
    from app.database.connection import SessionLocal
    from app.database.models import Job

    db = SessionLocal()
    try:
        db.query(Job).filter(Job.company == COMPANY).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_deshabilitado_sin_token(monkeypatch):
    from app.services import telegram as tg

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert tg.enabled() is False
    with pytest.raises(tg.TelegramError) as exc:
        tg.start_link(object(), UID)
    assert exc.value.code == "disabled"
    assert tg.notify_new_jobs(object(), UID, ["1"]) == {
        "sent": 0, "skipped": 0, "errors": []}


def test_link_start_y_confirm_por_webhook(_env, _auth, monkeypatch):
    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        started = client.post("/telegram/link/start",
                              headers=headers).json()
        assert started["deep_link"].startswith(
            "https://t.me/test_job_bot?start=")
        code = started["code"]
        # Sin codigo: instrucciones, no vincula.
        plain = client.post("/telegram/webhook?secret=testsecret",
                            json={"message": {"text": "/start",
                                              "chat": {"id": 111},
                                              "from": {}}})
        assert plain.status_code == 200
        st = client.get("/telegram/status", headers=headers).json()
        assert st["connected"] is False
        # Con codigo: vincula al uid autenticado.
        done = client.post("/telegram/webhook?secret=testsecret", json={
            "message": {"text": f"/start {code}", "chat": {"id": 111},
                        "from": {"username": "tester"}}})
        assert done.status_code == 200
        assert done.json()["uid"] == UID
        st = client.get("/telegram/status", headers=headers).json()
        assert st["connected"] is True
        assert st["username"] == "tester"
        assert st["valid"] is True
        # Codigo de un solo uso.
        again = client.post("/telegram/webhook?secret=testsecret", json={
            "message": {"text": f"/start {code}", "chat": {"id": 222},
                        "from": {}}})
        assert again.status_code == 200
        # Secreto malo: 401.
        bad = client.post("/telegram/webhook?secret=otro", json={})
        assert bad.status_code == 401


def test_chat_no_se_vincula_a_dos_cuentas(_env, _auth, monkeypatch):
    import app.auth as auth_module

    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        code = client.post("/telegram/link/start",
                           headers=headers).json()["code"]
        client.post("/telegram/webhook?secret=testsecret", json={
            "message": {"text": f"/start {code}", "chat": {"id": 333},
                        "from": {}}})
        code2 = client.post("/telegram/link/start",
                            headers=headers).json()["code"]
        # Mismo chat, OTRO uid: se rechaza.
        auth_module.verify_bearer_token = lambda h: {
            "uid": UID2, "email": "b@t.t", "name": "B"}
        code3 = client.post(
            "/telegram/link/start",
            headers={"Authorization": "Bearer y"}).json()["code"]
        try:
            from app.services import telegram as tg

            from app.database.connection import SessionLocal

            db = SessionLocal()
            try:
                with pytest.raises(tg.TelegramError) as exc:
                    tg.confirm_link(db, code3, 333, None)
                assert exc.value.code == "already_linked"
            finally:
                db.close()
        finally:
            pass


def test_test_y_unlink(_env, _auth, monkeypatch):
    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        assert client.post("/telegram/test",
                           headers=headers).status_code == 502
        code = client.post("/telegram/link/start",
                           headers=headers).json()["code"]
        client.post("/telegram/webhook?secret=testsecret", json={
            "message": {"text": f"/start {code}", "chat": {"id": 444},
                        "from": {}}})
        ok = client.post("/telegram/test", headers=headers)
        assert ok.status_code == 200
        assert ok.json()["message_id"] == 77
        assert client.delete("/telegram", headers=headers).status_code == 204
        st = client.get("/telegram/status", headers=headers).json()
        assert st["connected"] is False


def test_aviso_idempotente_y_con_boton(_env, monkeypatch):
    import httpx

    seen = {}

    def fake_post(url, json=None, timeout=None):
        seen["payload"] = json
        return FakeResponse(200, {"ok": True,
                                  "result": {"message_id": 5}})

    monkeypatch.setattr(httpx, "post", fake_post)
    from app.database.connection import SessionLocal
    from app.services import telegram as tg

    job_id = _make_job()
    try:
        db = SessionLocal()
        try:
            from app.database.models import TelegramLink

            db.merge(TelegramLink(uid=UID, chat_id="999"))
            db.commit()
            from app.services.job_service import get_job_by_id

            job = get_job_by_id(db, job_id)
            text, keyboard = tg.build_job_message(job)
            assert "Analista Telegram" in text
            assert COMPANY in text
            assert "Bogota" in text
            assert "$3.000.000" in text
            assert keyboard["inline_keyboard"][0][0]["text"] == \
                "Ver oferta"
            assert keyboard["inline_keyboard"][0][0]["url"] == \
                "https://example.com/tg-1"
            first = tg.send_job(db, UID, job)
            assert first == 5
            assert tg.send_job(db, UID, job) is None
            assert tg.was_sent(db, UID, job_id) is True
        finally:
            db.close()
    finally:
        _clean_jobs()


def test_bloqueo_marca_invalido_sin_reventar(_env, monkeypatch):
    import httpx

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/sendMessage"):
            return FakeResponse(403, {"ok": False,
                                      "description": "Forbidden: bot was "
                                                     "blocked by the user"})
        return FakeResponse(200, {"ok": True, "result": {}})

    monkeypatch.setattr(httpx, "post", fake_post)
    from app.database.connection import SessionLocal
    from app.services import telegram as tg

    job_id = _make_job(url="https://example.com/tg-2")
    try:
        db = SessionLocal()
        try:
            from app.database.models import TelegramLink

            db.merge(TelegramLink(uid=UID, chat_id="555"))
            db.commit()
            summary = tg.notify_new_jobs(db, UID, [job_id])
            assert summary["sent"] == 0
            assert summary["errors"]
            row = db.query(TelegramLink).filter(
                TelegramLink.uid == UID).first()
            assert row.invalid == 1
        finally:
            db.close()
    finally:
        _clean_jobs()


def test_hook_scheduler_no_rompe_busqueda(_env, monkeypatch):
    import httpx

    def fake_post(url, json=None, timeout=None):
        raise AssertionError("sin red en este test")

    monkeypatch.setattr(httpx, "post", fake_post)
    from app.services import telegram as tg

    # Sin link ni token util: resumen vacio, sin excepciones.
    assert tg.notify_new_jobs(object(), None, ["1"])["sent"] == 0
