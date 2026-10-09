"""API keys propias por usuario: cifrado, estado y fallback.

Sin red: verificacion en vivo simulada y proveedores stub.
Nunca debe exponerse material de keys al cliente.
"""
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.ai.user_providers import ProviderError
from app.main import app

UID = "uid-aikeys"


@pytest.fixture()
def _secret(monkeypatch):
    monkeypatch.setenv("AI_KEYS_SECRET", Fernet.generate_key().decode())
    from app.database.connection import Base, engine

    Base.metadata.create_all(bind=engine)
    yield
    from app.database.connection import SessionLocal
    from app.database.models import UserAIKey

    db = SessionLocal()
    try:
        db.query(UserAIKey).filter(UserAIKey.uid == UID).delete(
            synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _db():
    from app.database.connection import SessionLocal

    return SessionLocal()


def test_crypto_roundtrip_sin_exponer(_secret):
    from app.services import ai_keys

    enc = ai_keys.encrypt_key("sk-test-12345678")
    assert "sk-test" not in enc
    assert ai_keys.decrypt_key(enc) == "sk-test-12345678"


def test_sin_secreto_se_niega(_secret, monkeypatch):
    from app.services import ai_keys

    monkeypatch.delenv("AI_KEYS_SECRET")
    with pytest.raises(RuntimeError):
        ai_keys.encrypt_key("sk-test-12345678")


def test_validaciones(_secret):
    from app.services import ai_keys

    db = _db()
    try:
        with pytest.raises(ValueError):
            ai_keys.set_key(db, UID, "noexiste", "sk-test-12345678")
        with pytest.raises(ValueError):
            ai_keys.set_key(db, UID, "openai", "corta")
    finally:
        db.close()


def test_prefijo_no_bloquea_key_valida(_secret, monkeypatch):
    """El prefijo (AIza, sk-, ...) es ayuda, no validacion: una key
    con formato no estandar se acepta si el proveedor la verifica."""
    from app.services import ai_keys

    monkeypatch.setattr("app.services.ai_keys._live_verify",
                        lambda provider, key: None)
    db = _db()
    try:
        saved = ai_keys.set_key(db, UID, "gemini", "sk-test-12345678")
        assert saved["configured"] is True
        assert saved["status"] == "disponible"
    finally:
        db.close()


def test_limpia_espacios_y_rechazo_auth(_secret, monkeypatch):
    from app.ai.user_providers import ProviderError
    from app.services import ai_keys

    def fake_verify(provider, key):
        assert " " not in key and "\n" not in key
        raise ProviderError("auth", "API key rechazada (auth 400)")

    monkeypatch.setattr("app.services.ai_keys._live_verify", fake_verify)
    db = _db()
    try:
        with pytest.raises(ValueError, match="rechazada"):
            ai_keys.set_key(
                db, UID, "gemini", "  AIzaSy-test-con-espacios-123456\n")
    finally:
        db.close()


def test_clasifica_key_invalida_google():
    """El 400 de Google ('API key not valid') es auth, no 'unknown'."""
    from app.ai.user_providers import classify_http_error

    err = classify_http_error(
        400, '{"error": {"code": 400, "message": "API key not valid. '
        'Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}',
        "HTTPStatusError")
    assert err.code == "auth"


def test_clasifica_sin_saldo_como_quota():
    """DeepSeek 402 'Insufficient Balance' es quota (key valida)."""
    from app.ai.user_providers import classify_http_error

    err = classify_http_error(
        402, '{"error": {"message": "Insufficient Balance", '
        '"type": "unknown_error", "code": "invalid_request_error"}}',
        "HTTPStatusError")
    assert err.code == "quota"


def test_sin_saldo_se_guarda_marcada(_secret, monkeypatch):
    """Key valida sin saldo: se guarda (cuota_agotada), no se rechaza."""
    from app.ai.user_providers import ProviderError
    from app.services import ai_keys

    def fake_verify(provider, key):
        raise ProviderError("quota", "Sin saldo: Insufficient Balance")

    monkeypatch.setattr("app.services.ai_keys._live_verify", fake_verify)
    db = _db()
    try:
        saved = ai_keys.set_key(db, UID, "deepseek", "sk-test-12345678")
        assert saved["configured"] is True
        assert saved["status"] == "cuota_agotada"
    finally:
        db.close()


def test_saturado_se_guarda_sin_verificar(_secret, monkeypatch):
    """503 transitorio (key aceptada): se guarda para usarla al
    recuperarse el proveedor, en vez de bloquear al usuario."""
    from app.ai.user_providers import ProviderError
    from app.services import ai_keys

    def fake_verify(provider, key):
        raise ProviderError("unavailable", "Timeout/conexion fallida")

    monkeypatch.setattr("app.services.ai_keys._live_verify", fake_verify)
    db = _db()
    try:
        saved = ai_keys.set_key(db, UID, "openai", "sk-test-12345678")
        assert saved["configured"] is True
        assert saved["status"] == "no_verificada"
    finally:
        db.close()


def test_status_no_filtra_keys(_secret, monkeypatch):
    from app.services import ai_keys

    monkeypatch.setattr("app.services.ai_keys._live_verify",
                        lambda provider, key: None)
    db = _db()
    try:
        saved = ai_keys.set_key(db, UID, "deepseek", "sk-test-12345678")
        assert saved["configured"] is True
        assert saved["status"] == "disponible"
        for row in ai_keys.list_status(db, UID):
            assert "sk-test" not in str(row)
            assert "key_enc" not in row
        assert ai_keys.delete_key(db, UID, "deepseek") is True
        assert ai_keys.delete_key(db, UID, "deepseek") is False
    finally:
        db.close()


class _QuotaThenOk:
    id = "stub_a"
    label = "Stub A"
    model = "stub"
    key_help = ""
    calls = 0

    def complete(self, system, user, api_key, timeout):
        type(self).calls += 1
        if type(self).calls == 1:
            raise ProviderError("quota", "Cuota agotada: blah")
        return '{"summary": "ok"}'


class _AlwaysOk:
    id = "stub_b"
    label = "Stub B"
    model = "stub"
    key_help = ""

    def complete(self, system, user, api_key, timeout):
        return '{"summary": "ok"}'


@pytest.fixture()
def _stubs(monkeypatch):
    _QuotaThenOk.calls = 0
    monkeypatch.setattr("app.ai.user_providers.SUPPORTED",
                        {"stub_a": _QuotaThenOk(),
                         "stub_b": _AlwaysOk()})
    return _QuotaThenOk, _AlwaysOk


def test_fallback_cuota_y_preferido(_secret, _stubs):
    from app.ai import user_llm
    from app.services import ai_keys

    db = _db()
    try:
        ai_keys._save_row(db, UID, "stub_a", ai_keys.encrypt_key("k1"*8),
                          "disponible", "")
        ai_keys._save_row(db, UID, "stub_b", ai_keys.encrypt_key("k2"*8),
                          "disponible", "")
        # Preferido con cuota -> fallback automatico al otro.
        client = user_llm.for_user(db, UID, preferred="stub_a")
        assert client is not None
        text = client.generate("sys", "hola")
        assert text == '{"summary": "ok"}'
        assert client.provider_used == "stub_b"
        statuses = {r["provider"]: r["status"]
                    for r in ai_keys.list_status(db, UID)}
        assert statuses["stub_a"] == "cuota_agotada"
        assert statuses["stub_b"] == "disponible"
        # Sin preferido: primero disponible.
        client2 = user_llm.for_user(db, UID)
        assert client2 is not None
    finally:
        db.close()


def test_sin_keys_deterministico(_secret):
    from app.ai import user_llm

    db = _db()
    try:
        assert user_llm.for_user(db, "nadie") is None
        assert user_llm.for_user(db, None) is None
    finally:
        db.close()


def test_polish_y_rewrite_con_cliente(_secret):
    from app.ai import user_llm

    class _Fake:
        provider_used = "stub_b"

        def generate(self, system, user):
            return ('{"summary": "Resumen adaptado al cargo con '
                    'experiencia suficiente."}')

    out = user_llm.polish_summary_for_user(
        _Fake(), "Resumen original largo suficiente.", "Dev", ["Python"])
    assert out["provider"] == "stub_b"
    assert "adaptado" in out["summary"]

    class _FakeBullets(_Fake):
        def generate(self, system, user):
            return ('{"bullets": ["Analice datos con Python para '
                    'reportes."]}')

    out = user_llm.rewrite_bullets_for_user(
        _FakeBullets(), ["Analice datos con Python para reportes."],
        ["Python"], "Dev")
    assert out["verified"] is True


def test_endpoints_status_sin_keys(_secret):
    import app.auth as auth_module

    orig = auth_module.verify_bearer_token
    auth_module.verify_bearer_token = lambda h: {
        "uid": UID, "email": "a@b.co", "name": "A"}
    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer x"}
            providers = client.get("/ai-keys/providers").json()
            assert {"gemini", "deepseek", "openai"} <= {
                p["id"] for p in providers["providers"]}
            status = client.get("/ai-keys/status",
                                headers=headers).json()
            for row in status["providers"]:
                assert set(row) == {
                    "provider", "label", "model", "key_help",
                    "configured", "status", "detail", "updated_at"}
                assert row["configured"] is False
            bad = client.put("/ai-keys/nope", json={"key": "x"*16},
                             headers=headers)
            assert bad.status_code == 400
    finally:
        auth_module.verify_bearer_token = orig


def test_adapt_una_sola_consulta_texto_plano():
    """Resumen + bullets en 1 generate(), prompt solo con texto plano
    (titulo/skills/descripcion oferta + resumen/experiencias perfil),
    verificado contra originales."""
    from app.ai import user_llm

    calls = []

    class _Fake:
        provider_used = "groq"

        def generate(self, system, user):
            calls.append((system, user))
            assert isinstance(system, str) and isinstance(user, str)
            return ('{"summary": "Analista de datos con Python para '
                    'reportes y tableros.", "experiences": '
                    '[{"index": 0, "bullets": ["Analice datos con Python '
                    'para reportes."]}]}')

    out = user_llm.adapt_profile_for_user(
        _Fake(), job_title="Analista de Datos", job_company="Acme",
        job_description="Buscamos analista con Python para reportes.",
        job_skills=["Python", "SQL"],
        profile_summary="Analista de datos con Python para reportes.",
        experiences=[{"title": "Analista", "company": "Acme",
                      "bullets": ["Analice datos con Python para reportes."]}],
        allowed_skills=["Python"], target_role="Analista de Datos")
    assert len(calls) == 1
    system, prompt = calls[0]
    assert "Analista de Datos" in prompt
    assert "Python" in prompt
    assert "Buscamos analista" in prompt
    assert "Analice datos" in prompt
    assert ".pdf" not in prompt and "bytes" not in prompt.lower()
    assert out["provider"] == "groq"
    assert out["experiences"] == [
        {"index": 0,
         "bullets": ["Analice datos con Python para reportes."]}]


def test_adapt_invento_o_mal_json_falla():
    """Tecnologia nueva o JSON invalido -> ValueError (el llamador usa
    el flujo deterministico)."""
    from app.ai import user_llm

    class _FakeInventa:
        provider_used = "groq"

        def generate(self, system, user):
            return ('{"summary": "Analista de datos con Python para '
                    'reportes y tableros.", "experiences": '
                    '[{"index": 0, "bullets": ["Lidere equipo con Rust '
                    'para compilar."]}]}')

    import pytest as _pytest

    with _pytest.raises(ValueError):
        user_llm.adapt_profile_for_user(
            _FakeInventa(), job_title="Dev", job_company="",
            job_description="Python", job_skills=[],
            profile_summary="Analista de datos con Python para reportes.",
            experiences=[{"title": "A", "company": "",
                          "bullets": ["Analice datos con Python."]}],
            allowed_skills=["Python"], target_role="Dev")

    class _FakeRoto:
        provider_used = "groq"

        def generate(self, system, user):
            return "esto no es json"

    with _pytest.raises(ValueError):
        user_llm.adapt_profile_for_user(
            _FakeRoto(), job_title="Dev", job_company="",
            job_description="Python", job_skills=[],
            profile_summary="Analista de datos con Python para reportes.",
            experiences=[], allowed_skills=[], target_role="Dev")


def test_catalogo_incluye_groq_y_openrouter():
    from app.ai import user_providers as providers

    assert {"groq", "openrouter"} <= set(providers.SUPPORTED)
    assert providers.SUPPORTED["groq"].model == "openai/gpt-oss-120b"
    assert ":free" in providers.SUPPORTED["openrouter"].model


def test_groq_y_openrouter_peticion_correcta(monkeypatch):
    """URL, Bearer, modelo y (OpenRouter) headers propios. Sin
    response_format: varios gratuitos lo rechazan."""
    import httpx

    from app.ai import user_providers as providers

    seen = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        seen["json"] = json
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    out = providers.SUPPORTED["groq"].complete(
        "sys", "hola", "gsk-test-12345678", 10)
    assert out == '{"ok": true}'
    assert seen["url"] == \
        "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer gsk-test-12345678"
    assert seen["json"]["model"] == "openai/gpt-oss-120b"
    assert "response_format" not in seen["json"]

    out = providers.SUPPORTED["openrouter"].complete(
        "sys", "hola", "sk-or-test-12345678", 10)
    assert out == '{"ok": true}'
    assert seen["url"] == \
        "https://openrouter.ai/api/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-or-test-12345678"
    assert seen["headers"]["HTTP-Referer"]
    assert seen["headers"]["X-Title"] == "Job Agent"
    assert seen["json"]["model"].endswith(":free")
    assert "response_format" not in seen["json"]
