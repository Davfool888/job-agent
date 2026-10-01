"""Autenticacion con Firebase Auth (Google provider).

El frontend hace signInWithPopup(Google) y envia el ID token en
`Authorization: Bearer <token>`. Aqui se verifica con Admin SDK y se
devuelve/crea el usuario en la coleccion/tabla `users`.

Si no hay credenciales de Firebase (desarrollo sin login), la
verificacion falla con 401 honesto; el frontend muestra /login igual.
"""
from __future__ import annotations

from fastapi import Header, HTTPException


def _get_admin_auth():
    try:
        from firebase_admin import auth as admin_auth

        # Asegura app inicializada (reusa firestore_client).
        from app.database import firestore_client

        firestore_client.get_firestore()
        return admin_auth
    except Exception as exc:  # pragma: no cover - sin credenciales
        raise HTTPException(
            status_code=503,
            detail=f"Firebase Admin no configurado: {exc}",
        )


def verify_bearer_token(authorization: str | None) -> dict:
    """Verifica `Bearer <idToken>` y devuelve {uid, email, name}."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Falta token de sesion.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token vacio.")
    admin_auth = _get_admin_auth()
    try:
        decoded = admin_auth.verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Sesion invalida o vencida.")
    return {
        "uid": decoded.get("uid", ""),
        "email": (decoded.get("email") or "").strip().lower(),
        "name": (decoded.get("name") or "").strip(),
    }


def optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    if not authorization:
        return None
    try:
        return verify_bearer_token(authorization)
    except HTTPException:
        return None
