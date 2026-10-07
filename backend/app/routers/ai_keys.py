"""APIs de IA propias por usuario (cuota propia, nunca global).

- GET /ai-keys/providers: catalogo publico (sin secretos).
- GET /ai-keys/status: estado por proveedor del usuario (sin keys).
- PUT /ai-keys/{provider}: valida en vivo y guarda cifrada.
- DELETE /ai-keys/{provider}: borra la key.
"""
from typing import Any

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from sqlalchemy.orm import Session

from app.database.connection import get_db

router = APIRouter()


@router.get("/ai-keys/providers")
def ai_key_providers():
    """Proveedores soportados para keys propias (extensible)."""
    from app.ai.user_providers import SUPPORTED

    return {"providers": [
        {"id": pid, "label": spec.label, "model": spec.model,
         "key_help": spec.key_help}
        for pid, spec in sorted(SUPPORTED.items())
    ]}


def _uid_or_401(request: Request) -> str:
    from app.auth import verify_bearer_token

    try:
        claims = verify_bearer_token(request.headers.get("authorization"))
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=401,
                            detail=f"Sesion invalida: {error}")
    uid = claims.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Sesion invalida.")
    return uid


@router.get("/ai-keys/status")
def ai_keys_status(request: Request, db: Session = Depends(get_db)):
    """Estado por proveedor (configurado/disponible/cuota/error).

    NUNCA incluye material de keys.
    """
    from app.services import ai_keys

    return {"providers": ai_keys.list_status(db, _uid_or_401(request))}


@router.put("/ai-keys/{provider}")
def ai_key_save(provider: str, payload: dict[str, Any],
                request: Request, db: Session = Depends(get_db)):
    """Valida en vivo contra el proveedor y guarda cifrada."""
    from app.services import ai_keys

    uid = _uid_or_401(request)
    try:
        saved = ai_keys.set_key(db, uid, provider,
                                (payload or {}).get("key"))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error))
    return saved


@router.delete("/ai-keys/{provider}", status_code=204)
def ai_key_delete(provider: str, request: Request,
                  db: Session = Depends(get_db)):
    from app.ai.user_providers import SUPPORTED
    from app.services import ai_keys

    if provider not in SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Proveedor desconocido: {provider}.")
    ai_keys.delete_key(db, _uid_or_401(request), provider)
    return None
