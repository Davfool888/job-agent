"""Telegram multi-bot: cada usuario pega su key, vincula y recibe avisos.

Todo con HTTP simulado (sin red real) y SQLite local.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

UID = "uid-tg-test"
EMAIL = "tg@test.test"
UID2 = "uid-tg-test-2"
COMPANY = "Empresa Telegram Test"

VALID_TOKEN = "123456:AAH-valid-token-para-test-1234567890"
BAD_TOKEN = "MALO123:AAH-token-rechazado-por-telegram-00000"


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture()
def _env(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("AI_KEYS_SECRET", Fernet.generate_key().decode())
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME", raising=False)
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

    def fake(authorization, uid=UID, email=EMAIL):
        assert (authorization or "").startswith("Bearer ")
        return {"uid": uid, "email": email, "name": "T"}

    monkeypatch.setattr(auth_module, "verify_bearer_token", fake)


def _ok_sender(monkeypatch, message_id=77, calls=None):
    import httpx

    def fake_post(url, json=None, timeout=None):
        if calls is not None:
            calls.append((url, json))
        if url.endswith("/getMe"):
            token = url.split("/bot", 1)[1].rsplit("/", 1)[0]
            if token.startswith("MALO"):
                return FakeResponse(401, {"ok": False,
                                          "description": "Unauthorized"})
            return FakeResponse(200, {"ok": True,
                                      "result": {"id": 1,
                                                 "username": "mi_bot_test"}})
        if url.endswith("/setWebhook"):
            return FakeResponse(200, {"ok": True, "result": True})
        if url.endswith("/deleteWebhook"):
            return FakeResponse(200, {"ok": True, "result": True})
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


def _user_secret(uid=UID):
    from app.database.connection import SessionLocal
    from app.database.models import TelegramLink

    db = SessionLocal()
    try:
        row = db.query(TelegramLink).filter(
            TelegramLink.uid == uid).first()
        return row.webhook_secret if row else None
    finally:
        db.close()


def test_sin_bot_pide_configurar(_env, _auth):
    from app.services import telegram as tg

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        st = client.get("/telegram/status", headers=headers).json()
        assert st["has_bot"] is False
        assert st["connected"] is False
        bad = client.post("/telegram/link/start", headers=headers)
        assert bad.status_code == 502
        assert "Configuración" in bad.json()["detail"]
        assert client.post("/telegram/test",
                           headers=headers).status_code == 502


def test_guardar_bot_formato_invalido(_env, _auth):
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        bad = client.post("/telegram/bot", headers=headers,
                          json={"token": "no-es-un-token"})
        assert bad.status_code == 400
        empty = client.post("/telegram/bot", headers=headers, json={})
        assert empty.status_code == 400


def test_guardar_bot_rechazado_por_telegram(_env, _auth, monkeypatch):
    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        bad = client.post("/telegram/bot", headers=headers,
                          json={"token": BAD_TOKEN})
        assert bad.status_code == 400
        assert "BotFather" in bad.json()["detail"]


def test_guardar_bot_autoconfigura_webhook(_env, _auth, monkeypatch):
    monkeypatch.setenv("TELEGRAM_PUBLIC_URL", "https://api.test.test")
    calls: list = []
    _ok_sender(monkeypatch, calls=calls)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        saved = client.post("/telegram/bot", headers=headers,
                            json={"token": VALID_TOKEN}).json()
        assert saved["has_bot"] is True
        assert saved["bot_username"] == "mi_bot_test"
        assert saved["webhook_ok"] is True
        sethooks = [c for c in calls if c[0].endswith("/setWebhook")]
        assert len(sethooks) == 1
        assert sethooks[0][1]["url"] == \
            f"https://api.test.test/telegram/webhook?uid={UID}"
        assert sethooks[0][1]["secret_token"]
        st = client.get("/telegram/status", headers=headers).json()
        assert st["has_bot"] is True
        assert st["bot_username"] == "mi_bot_test"


def test_guardar_bot_sin_public_url_da_manual(_env, _auth, monkeypatch):
    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        saved = client.post("/telegram/bot", headers=headers,
                            json={"token": VALID_TOKEN}).json()
        assert saved["has_bot"] is True
        assert saved["webhook_ok"] is False
        assert "<TU_TOKEN>" in saved["manual_url"]
        assert saved["manual_secret"]


def test_link_start_y_confirm_por_webhook(_env, _auth, monkeypatch):
    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        client.post("/telegram/bot", headers=headers,
                    json={"token": VALID_TOKEN})
        started = client.post("/telegram/link/start",
                              headers=headers).json()
        assert started["deep_link"].startswith(
            "https://t.me/mi_bot_test?start=")
        code = started["code"]
        secret = _user_secret()
        assert secret
        # Sin codigo: instrucciones, no vincula.
        plain = client.post(
            f"/telegram/webhook?uid={UID}",
            headers={"X-Telegram-Bot-Api-Secret-Token": secret},
            json={"message": {"text": "/start",
                              "chat": {"id": 111}, "from": {}}})
        assert plain.status_code == 200
        st = client.get("/telegram/status", headers=headers).json()
        assert st["connected"] is False
        # Con codigo: vincula al uid autenticado.
        done = client.post(
            f"/telegram/webhook?uid={UID}&secret={secret}", json={
                "message": {"text": f"/start {code}", "chat": {"id": 111},
                            "from": {"username": "tester"}}})
        assert done.status_code == 200
        assert done.json()["uid"] == UID
        st = client.get("/telegram/status", headers=headers).json()
        assert st["connected"] is True
        assert st["username"] == "tester"
        assert st["valid"] is True
        # Codigo de un solo uso.
        again = client.post(
            f"/telegram/webhook?uid={UID}&secret={secret}", json={
                "message": {"text": f"/start {code}", "chat": {"id": 222},
                            "from": {}}})
        assert again.status_code == 200
        # Secreto malo: 401.
        bad = client.post(f"/telegram/webhook?uid={UID}&secret=otro",
                          json={})
        assert bad.status_code == 401


def test_chat_no_se_vincula_a_dos_cuentas(_env, _auth, monkeypatch):
    import app.auth as auth_module

    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        client.post("/telegram/bot", headers=headers,
                    json={"token": VALID_TOKEN})
        secret = _user_secret()
        code = client.post("/telegram/link/start",
                           headers=headers).json()["code"]
        client.post(f"/telegram/webhook?uid={UID}&secret={secret}", json={
            "message": {"text": f"/start {code}", "chat": {"id": 333},
                        "from": {}}})
        code2 = client.post("/telegram/link/start",
                            headers=headers).json()["code"]
        assert code2
        # Mismo chat, OTRO uid (con su propio bot): se rechaza.
        auth_module.verify_bearer_token = lambda h: {
            "uid": UID2, "email": "b@t.t", "name": "B"}
        client.post("/telegram/bot",
                    headers={"Authorization": "Bearer y"},
                    json={"token": VALID_TOKEN})
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


def test_test_y_quitar_bot(_env, _auth, monkeypatch):
    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        assert client.post("/telegram/test",
                           headers=headers).status_code == 502
        client.post("/telegram/bot", headers=headers,
                    json={"token": VALID_TOKEN})
        secret = _user_secret()
        code = client.post("/telegram/link/start",
                           headers=headers).json()["code"]
        client.post(f"/telegram/webhook?uid={UID}&secret={secret}", json={
            "message": {"text": f"/start {code}", "chat": {"id": 444},
                        "from": {}}})
        ok = client.post("/telegram/test", headers=headers)
        assert ok.status_code == 200
        assert ok.json()["message_id"] == 77
        assert client.delete("/telegram", headers=headers).status_code == 204
        st = client.get("/telegram/status", headers=headers).json()
        assert st["connected"] is False
        assert st["has_bot"] is True  # el bot se conserva al desvincular
        assert client.delete(
            "/telegram/bot", headers=headers).status_code == 204
        st = client.get("/telegram/status", headers=headers).json()
        assert st["has_bot"] is False


def _link_with_bot(monkeypatch, uid=UID, chat_id="999"):
    _ok_sender(monkeypatch)
    from app.database.connection import SessionLocal
    from app.database.models import TelegramLink
    from app.services import telegram as tg

    db = SessionLocal()
    try:
        tg.set_user_bot(db, uid, VALID_TOKEN)
        db.merge(TelegramLink(uid=uid, chat_id=str(chat_id)))
        db.commit()
    finally:
        db.close()


def test_aviso_idempotente_y_con_boton(_env, monkeypatch):
    import httpx

    seen = {}

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/getMe"):
            return FakeResponse(200, {"ok": True,
                                      "result": {"username": "mi_bot_test"}})
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
            tg.set_user_bot(db, UID, VALID_TOKEN)
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
        if url.endswith("/getMe"):
            return FakeResponse(200, {"ok": True,
                                      "result": {"username": "mi_bot_test"}})
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
            tg.set_user_bot(db, UID, VALID_TOKEN)
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

    # Sin link ni token util: no envia nada y no lanza excepciones.
    assert tg.notify_new_jobs(object(), None, ["1"])["sent"] == 0
    assert tg.notify_new_jobs(object(), UID, ["1"])["sent"] == 0


def test_bot_global_legacy_sigue_funcionando(_env, _auth, monkeypatch):
    """Instalaciones con TELEGRAM_BOT_TOKEN no exigen key propia."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "GLOBAL123")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "bot_global")
    _ok_sender(monkeypatch)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer x"}
        st = client.get("/telegram/status", headers=headers).json()
        assert st["has_bot"] is True
        assert st["bot_username"] == "bot_global"
        started = client.post("/telegram/link/start",
                              headers=headers).json()
        assert started["deep_link"].startswith(
            "https://t.me/bot_global?start=")
