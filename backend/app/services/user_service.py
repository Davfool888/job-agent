"""Usuarios de la app (login con Google).

Solo guarda: uid (Firebase), email (gmail), nombre y telefono.
Funciona en SQLite (tabla users) y Firestore (coleccion users/{uid}).
"""
from __future__ import annotations

from datetime import datetime


def get_user(db, uid: str) -> dict | None:
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as fs

        return fs.get_user(db, uid)
    from app.database.models import User

    row = db.query(User).filter(User.uid == uid).first()
    if not row:
        return None
    return {
        "uid": row.uid,
        "email": row.email or "",
        "nombre": row.nombre or "",
        "telefono": row.telefono or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_or_create_user(db, uid: str, email: str, nombre: str = "") -> tuple[dict, bool]:
    """Devuelve (user, created). No pisa nombre/telefono existentes."""
    existing = get_user(db, uid)
    if existing:
        return existing, False
    now = datetime.utcnow()
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as fs

        user = fs.save_user(db, uid, {
            "email": email,
            "nombre": nombre,
            "telefono": "",
            "created_at": now,
            "updated_at": now,
        })
        return user, True
    from app.database.models import User

    row = User(uid=uid, email=email, nombre=nombre, telefono="",
               created_at=now, updated_at=now)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "uid": row.uid,
        "email": row.email or "",
        "nombre": row.nombre or "",
        "telefono": row.telefono or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }, True


def update_user(db, uid: str, nombre: str | None = None,
                telefono: str | None = None) -> dict:
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as fs

        current = fs.get_user(db, uid) or {}
        fields: dict = {"updated_at": datetime.utcnow()}
        if nombre is not None:
            fields["nombre"] = nombre.strip()
        if telefono is not None:
            fields["telefono"] = telefono.strip()
        # Preserva email/created_at.
        for key in ("email", "created_at"):
            if key in current and key not in fields:
                fields[key] = current[key]
        return fs.save_user(db, uid, fields)
    from app.database.models import User

    row = db.query(User).filter(User.uid == uid).first()
    if not row:
        raise ValueError("Usuario no encontrado.")
    if nombre is not None:
        row.nombre = nombre.strip()
    if telefono is not None:
        row.telefono = telefono.strip()
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "uid": row.uid,
        "email": row.email or "",
        "nombre": row.nombre or "",
        "telefono": row.telefono or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
