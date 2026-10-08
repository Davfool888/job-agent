"""API keys de IA por usuario (cuota propia, jamas global).

Almacenamiento: Fernet con AI_KEYS_SECRET (el servidor sin secreto se
niega a guardar). Al frontend solo sale estado (configurado/valido/
disponible/cuota/error): NUNCA el material de la key, ni en logs.
"""
from __future__ import annotations

from datetime import datetime

STATUS_OK = "disponible"
STATUS_QUOTA = "cuota_agotada"
STATUS_ERROR = "error"
STATUS_UNVERIFIED = "no_verificada"

_VERIFY_TIMEOUT = 25


def _cipher():
    import os as _os

    from cryptography.fernet import Fernet

    secret = (_os.getenv("AI_KEYS_SECRET") or "").strip()
    if not secret:
        raise RuntimeError(
            "Servidor sin AI_KEYS_SECRET: no se pueden guardar API keys "
            "de usuario. Define un secreto de 32 bytes en base64.")
    # Formatos aceptados: Fernet key (44 chars) o hex de 64 (32 bytes).
    if len(secret) == 44:
        try:
            return Fernet(secret.encode())
        except Exception as error:
            raise RuntimeError(f"AI_KEYS_SECRET invalido: {error}")
    try:
        raw = bytes.fromhex(secret)
        if len(raw) != 32:
            raise ValueError()
        import base64 as _b64

        return Fernet(_b64.urlsafe_b64encode(raw))
    except Exception as error:
        raise RuntimeError(
            "AI_KEYS_SECRET invalido: usa Fernet key (44 chars) o "
            f"hex de 64. ({error})")


def encrypt_key(raw: str) -> str:
    return _cipher().encrypt(raw.encode()).decode()


def decrypt_key(enc: str) -> str:
    return _cipher().decrypt(enc.encode()).decode()


def _public_row(provider: str, row) -> dict:
    from app.ai.user_providers import SUPPORTED

    spec = SUPPORTED[provider]
    status = (row.status if row is not None else None) or STATUS_UNVERIFIED
    return {
        "provider": provider,
        "label": spec.label,
        "model": spec.model,
        "key_help": spec.key_help,
        "configured": row is not None,
        "status": status if row is not None else "no_configurado",
        "detail": (row.detail if row is not None else ""),
        "updated_at": row.updated_at.isoformat()
        if row is not None and row.updated_at else None,
    }


def _get_row(db, uid: str, provider: str):
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        snap = db.collection("user_ai_keys").document(
            f"{uid}:{provider}").get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}

        class _Row:
            pass

        row = _Row()
        row.status = data.get("status", STATUS_UNVERIFIED)
        row.detail = data.get("detail", "")
        row.key_enc = data.get("key_enc", "")
        row.updated_at = data.get("updated_at")
        return row
    from app.database.models import UserAIKey

    return db.query(UserAIKey).filter(
        UserAIKey.uid == uid, UserAIKey.provider == provider).first()


def _save_row(db, uid: str, provider: str, key_enc: str,
              status: str, detail: str) -> None:
    from app.database.firestore_client import is_firestore

    now = datetime.utcnow()
    if is_firestore(db):
        db.collection("user_ai_keys").document(f"{uid}:{provider}").set({
            "uid": uid, "provider": provider, "key_enc": key_enc,
            "status": status, "detail": detail[:300],
            "updated_at": now,
        }, merge=True)
        return
    from app.database.models import UserAIKey

    row = db.query(UserAIKey).filter(
        UserAIKey.uid == uid, UserAIKey.provider == provider).first()
    if row is None:
        row = UserAIKey(uid=uid, provider=provider)
        db.add(row)
    row.key_enc = key_enc
    row.status = status
    row.detail = detail[:300]
    row.updated_at = now
    db.commit()


def list_status(db, uid: str) -> list[dict]:
    """Estado por proveedor (sin material de keys)."""
    from app.ai.user_providers import SUPPORTED

    return [_public_row(pid, _get_row(db, uid, pid))
            for pid in sorted(SUPPORTED)]


def configured_providers(db, uid: str) -> list[str]:
    """Ids con key guardada (para el selector y el fallback)."""
    from app.ai.user_providers import SUPPORTED

    return [pid for pid in sorted(SUPPORTED)
            if _get_row(db, uid, pid) is not None]


def get_key(db, uid: str, provider: str) -> str | None:
    """Material descifrado (USO INTERNO, jamas al cliente)."""
    row = _get_row(db, uid, provider)
    if row is None or not row.key_enc:
        return None
    return decrypt_key(row.key_enc)


def record_result(db, uid: str, provider: str, ok: bool,
                  code: str = "", message: str = "") -> None:
    """Actualiza estado tras un uso (cuota/rate/auth/offline)."""
    row = _get_row(db, uid, provider)
    if row is None:
        return
    if ok:
        status, detail = STATUS_OK, ""
    elif code == "quota":
        status, detail = STATUS_QUOTA, message or "Cuota agotada"
    elif code in ("auth",):
        status, detail = STATUS_ERROR, message or "Key rechazada"
    elif code in ("rate",):
        status, detail = STATUS_ERROR, message or "Rate limit"
    else:
        status, detail = STATUS_ERROR, message or "No disponible"
    _save_row(db, uid, provider, row.key_enc, status, detail)


def _live_verify(provider: str, raw_key: str) -> None:
    """Ping barato: clasifica la key o lanza ProviderError/ValueError."""
    from app.ai.user_providers import SUPPORTED

    spec = SUPPORTED[provider]
    spec.complete(
        "Responde exclusivamente con JSON valido.",
        'Responde {"ok": true}.', raw_key, _VERIFY_TIMEOUT)


def set_key(db, uid: str, provider: str, raw_key: str) -> dict:
    """Valida en vivo y guarda cifrada. Devuelve vista publica.

    El prefijo (AIza, sk-, ...) es SOLO ayuda visual: nunca rechaza.
    La autoridad es la verificacion en vivo contra el proveedor, porque
    los formatos cambian y un prefijo estricto bloquea keys validas.
    """
    import re as _re

    from app.ai.user_providers import SUPPORTED, ProviderError, get_spec

    get_spec(provider)  # ValueError si no soportado
    # Limpia espacios/saltos que se cuelan al copiar desde la web.
    raw_key = _re.sub(r"\s+", "", str(raw_key or ""))
    if len(raw_key) < 12:
        raise ValueError(
            "API key demasiado corta o incompleta "
            "(¿la copiaste entera desde la web del proveedor?).")
    try:
        _live_verify(provider, raw_key)
    except ProviderError as error:
        if error.code == "auth":
            raise ValueError(
                "La key fue rechazada por el proveedor "
                "(revisala y reintenta).")
        if error.code == "quota":
            # Key valida pero sin cuota: se guarda marcada.
            _save_row(db, uid, provider, encrypt_key(raw_key),
                      STATUS_QUOTA, str(error)[:200])
            return _public_row(provider, _get_row(db, uid, provider))
        if error.code == "unavailable":
            # La key paso auth pero el proveedor esta saturado/caido
            # (ej. Gemini 503): se guarda sin verificar y el estado se
            # actualiza sola al primer uso real.
            _save_row(db, uid, provider, encrypt_key(raw_key),
                      STATUS_UNVERIFIED,
                      f"Sin verificar (proveedor saturado): {error}"[:200])
            return _public_row(provider, _get_row(db, uid, provider))
        raise ValueError(f"Proveedor no verificable ahora: {error}")
    _save_row(db, uid, provider, encrypt_key(raw_key), STATUS_OK, "")
    return _public_row(provider, _get_row(db, uid, provider))


def delete_key(db, uid: str, provider: str) -> bool:
    """Borra la key del usuario. Devuelve si existia."""
    from app.database.firestore_client import is_firestore

    if _get_row(db, uid, provider) is None:
        return False
    if is_firestore(db):
        db.collection("user_ai_keys").document(f"{uid}:{provider}").delete()
        return True
    from app.database.models import UserAIKey

    db.query(UserAIKey).filter(
        UserAIKey.uid == uid, UserAIKey.provider == provider).delete(
            synchronize_session=False)
    db.commit()
    return True
