"""Conexion con Cloud Firestore via Firebase Admin SDK.

Solo el backend usa este modulo (jamas el frontend, jamas exponer keys).
Credenciales: GOOGLE_APPLICATION_CREDENTIALS (ruta al JSON de la cuenta
de servicio) o FIREBASE_SERVICE_ACCOUNT_JSON (JSON inline, util en Render).
Sin credenciales -> se usa el emulador si FIRESTORE_EMULATOR_HOST existe;
si no, error claro al primer uso (no al importar).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_client = None


def as_naive_utc(value):
    """Normaliza fecha a naive UTC para comparar sin TypeError.

    Firestore devuelve aware (tz UTC); SQLite devuelve naive; los
    JSON/ISO llegan como str. Mezclar aware+naive revienta con
    'can't subtract/compare offset-naive and offset-aware' — este
    helper es LA forma de comparar en todo el backend.
    Devuelve None si es irreconocible.
    """
    from datetime import datetime, timezone

    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    if hasattr(value, "isoformat"):
        try:
            return as_naive_utc(value.isoformat())
        except Exception:  # noqa: BLE001
            return None
    return None


def _resolve_key_path(raw: str) -> str | None:
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)
    try:
        from app.config import BASE_DIR, ROOT_DIR
    except Exception:
        BASE_DIR = ROOT_DIR = Path.cwd()
    for base in (ROOT_DIR, BASE_DIR, Path.cwd()):
        if (base / raw).exists():
            return str(base / raw)
    return None


def get_firestore():
    """Devuelve el cliente Firestore (singleton). Lanza RuntimeError
    explicativo si no hay credenciales ni emulador."""
    global _client
    if _client is not None:
        return _client

    if os.getenv("FIRESTORE_EMULATOR_HOST"):
        import firebase_admin
        from firebase_admin import firestore as fs_admin

        from app.config import FIREBASE_PROJECT_ID

        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(
                options={"projectId": FIREBASE_PROJECT_ID or "demo"}
            )
        _client = fs_admin.client()
        logger.info("Firestore: usando EMULADOR (%s)",
                     os.getenv("FIRESTORE_EMULATOR_HOST"))
        return _client

    inline = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    key_path = _resolve_key_path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""))
    inline_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_B64", "")
    if inline_b64 and not inline:
        # Robusto contra dashboards que rompen los saltos de linea del
        # JSON multilinea: el base64 viaja en una sola linea.
        try:
            import base64

            inline = base64.b64decode(inline_b64.strip()).decode("utf-8")
        except Exception as error:
            raise RuntimeError(
                "FIREBASE_SERVICE_ACCOUNT_B64 invalido (no es base64 "
                f"de un JSON): {error}"
            )
    if not inline and not key_path:
        raise RuntimeError(
            "Firestore sin credenciales: define GOOGLE_APPLICATION_CREDENTIALS "
            "(ruta al JSON) o FIREBASE_SERVICE_ACCOUNT_JSON (inline) o "
            "FIREBASE_SERVICE_ACCOUNT_B64 (base64, recomendado en Render) o "
            "FIRESTORE_EMULATOR_HOST. Ver database/.env.example"
        )

    import firebase_admin
    from firebase_admin import credentials, firestore as fs_admin

    from app.config import FIREBASE_PROJECT_ID
    from app.config import FIRESTORE_DATABASE

    try:
        firebase_admin.get_app()
    except ValueError:
        if inline:
            cred = credentials.Certificate(json.loads(inline))
        else:
            cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred, {
            "projectId": FIREBASE_PROJECT_ID or None,
        })
    if FIRESTORE_DATABASE and FIRESTORE_DATABASE != "(default)":
        _client = fs_admin.client(database_id=FIRESTORE_DATABASE)
    else:
        _client = fs_admin.client()
    logger.info("Firestore conectado (proyecto %s)", FIREBASE_PROJECT_ID)
    return _client


class FirestoreDatabase:
    """Handle opaco que viaja como `db` en los servicios cuando
    DB_BACKEND=firestore. Expone .client y nombre de colecciones."""

    def __init__(self):
        self.client = get_firestore()
        try:
            from app.config import FIRESTORE_DATABASE
        except Exception:
            FIRESTORE_DATABASE = "(default)"
        self.database = FIRESTORE_DATABASE or "(default)"

    def collection(self, name: str):
        return self.client.collection(name)


def is_firestore(db) -> bool:
    return isinstance(db, FirestoreDatabase)
