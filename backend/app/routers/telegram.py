"""Telegram fase 1: vinculacion + notificaciones de ofertas.

- POST /telegram/link/start (auth): codigo temporal + deep link.
- POST /telegram/webhook: lo llama Telegram (valida secreto + /start).
- GET /telegram/status (auth): conectado/valido sin exponer nada.
- POST /telegram/test (auth): mensaje de prueba (valida el canal).
- DELETE /telegram (auth): desconectar.
"""
from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from sqlalchemy.orm import Session

from app.database.connection import get_db

router = APIRouter()


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


@router.post("/telegram/link/start")
def telegram_link_start(request: Request, db: Session = Depends(get_db)):
    """Codigo temporal + deep link t.me para el usuario autenticado."""
    from app.services import telegram as tg

    try:
        return tg.start_link(db, _uid_or_401(request))
    except tg.TelegramError as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    secret: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Lo llama Telegram con cada mensaje. Solo procesa /start <codigo>.

    Fase 2 agregara aqui los callbacks Postularme/Descartar.
    """
    import os as _os

    from app.services import telegram as tg

    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    expected = (_os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if expected and secret != expected and header_secret != expected:
        raise HTTPException(status_code=401, detail="No autorizado.")
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": True}
    message = (update or {}).get("message") or {}
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not text.startswith("/start") or chat_id is None:
        return {"ok": True}
    parts = text.split()
    import logging as _logging

    _weblog = _logging.getLogger("job-agent.telegram.webhook")
    payload = parts[1].strip() if len(parts) > 1 else ""
    _weblog.warning("tg-webhook /start chat=%s con_payload=%s payload=%s...",
                    chat_id, bool(payload), payload[:4])
    if len(parts) < 2 or not parts[1].strip():
        try:
            tg._api("sendMessage", {
                "chat_id": chat_id,
                "text": "Hola 👋 Para vincular tu cuenta, abre Job Agent "
                        "→ Configuración → Conectar Telegram y usa el "
                        "botón que te lleva aquí.",
            })
        except tg.TelegramError:
            pass
        return {"ok": True}
    try:
        result = tg.confirm_link(db, parts[1].strip(), chat_id,
                                 str((message.get("from") or {}).get(
                                     "username") or ""))
    except tg.TelegramError as error:
        try:
            tg._api("sendMessage", {
                "chat_id": chat_id,
                "text": f"⚠ No se pudo vincular: {error}",
            })
        except tg.TelegramError:
            pass
        return {"ok": True}
    try:
        tg._api("sendMessage", {
            "chat_id": chat_id,
            "text": "✅ <b>Telegram vinculado con Job Agent</b>\n"
                    "Recibirás aquí las nuevas ofertas de tus búsquedas.",
            "parse_mode": "HTML",
        })
    except tg.TelegramError:
        pass
    return {"ok": True, "uid": result["uid"]}


@router.get("/telegram/status")
def telegram_status(request: Request, db: Session = Depends(get_db)):
    """Conectado/valido/username. Sin secretos."""
    from app.services import telegram as tg

    return tg.get_status(db, _uid_or_401(request))


@router.post("/telegram/test")
def telegram_test(request: Request, db: Session = Depends(get_db)):
    """Envia mensaje de prueba (valida el canal de punta a punta)."""
    from app.services import telegram as tg

    try:
        return tg.send_test(db, _uid_or_401(request))
    except tg.TelegramError as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.delete("/telegram", status_code=204)
def telegram_unlink(request: Request, db: Session = Depends(get_db)):
    from app.services import telegram as tg

    tg.unlink(db, _uid_or_401(request))
    return None
