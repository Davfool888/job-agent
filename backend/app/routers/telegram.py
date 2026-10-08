"""Telegram: bot propio por usuario + vinculacion + avisos.

- POST /telegram/bot (auth): guarda la key del bot propio (validada
  con getMe, cifrada) y registra su webhook. Sin secretos en respuesta.
- DELETE /telegram/bot (auth): borra el bot propio y desvincula el chat.
- POST /telegram/link/start (auth): codigo temporal + deep link.
- POST /telegram/webhook: lo llama Telegram (valida secreto + /start).
- GET /telegram/status (auth): conectado/valido/bot. Sin secretos.
- POST /telegram/test (auth): mensaje de prueba (valida el canal).
- DELETE /telegram (auth): desconectar chat (conserva el bot).
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


@router.post("/telegram/bot")
async def telegram_set_bot(request: Request, db: Session = Depends(get_db)):
    """Guarda el bot propio del usuario (key de BotFather).

    Body: {"token": "123:AAH..."}. Valida en vivo con getMe, cifra con
    Fernet, registra el webhook del bot. Nunca devuelve el token.
    """
    from app.services import telegram as tg

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    token = str((body or {}).get("token") or "").strip()
    if not token:
        raise HTTPException(status_code=400,
                            detail="Falta el token del bot.")
    try:
        return tg.set_user_bot(db, _uid_or_401(request), token)
    except tg.TelegramError as error:
        if error.code == "invalid_token":
            raise HTTPException(status_code=400, detail=str(error))
        if error.code == "disabled":
            raise HTTPException(status_code=500, detail=str(error))
        raise HTTPException(status_code=502, detail=str(error))


@router.delete("/telegram/bot", status_code=204)
def telegram_remove_bot(request: Request, db: Session = Depends(get_db)):
    """Borra el bot propio y desvincula el chat."""
    from app.services import telegram as tg

    tg.remove_user_bot(db, _uid_or_401(request))
    return None


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
    uid: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Lo llama Telegram con cada mensaje. Solo procesa /start <codigo>.

    Multi-bot: cada bot propio apunta aqui con ?uid=<dueno>; el secreto
    se valida contra el secreto propio de ese usuario (o el global
    legacy cuando no hay uid). Fase 2 agregara callbacks aqui.
    """
    import os as _os

    from app.services import telegram as tg

    header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    reply_token = ""
    if uid:
        link = tg._get_link(db, str(uid)) or {}
        expected = str(link.get("webhook_secret") or "").strip()
        if expected and secret != expected and header_secret != expected:
            raise HTTPException(status_code=401, detail="No autorizado.")
        try:
            reply_token = tg._user_token(db, str(uid))
        except tg.TelegramError:
            reply_token = ""
    else:
        expected = (_os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
        if expected and secret != expected and header_secret != expected:
            raise HTTPException(status_code=401, detail="No autorizado.")
        reply_token = tg._global_token()
    try:
        update = await request.json()
    except Exception:  # noqa: BLE001
        return {"ok": True}
    message = (update or {}).get("message") or {}
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = chat.get("id")

    def _reply(payload_text: str) -> None:
        if chat_id is None or not reply_token:
            return
        try:
            tg._api("sendMessage", {
                "chat_id": chat_id,
                "text": payload_text,
                "parse_mode": "HTML",
            }, reply_token)
        except tg.TelegramError:
            pass

    if not text.startswith("/start") or chat_id is None:
        return {"ok": True}
    parts = text.split()
    import logging as _logging

    _weblog = _logging.getLogger("job-agent.telegram.webhook")
    payload = parts[1].strip() if len(parts) > 1 else ""
    _weblog.warning("tg-webhook /start chat=%s con_payload=%s payload=%s...",
                    chat_id, bool(payload), payload[:4])
    if len(parts) < 2 or not parts[1].strip():
        _reply("Hola 👋 Para vincular tu cuenta, abre Job Agent "
               "→ Configuración → Conectar Telegram y usa el "
               "botón que te lleva aquí.")
        return {"ok": True}
    try:
        result = tg.confirm_link(db, parts[1].strip(), chat_id,
                                 str((message.get("from") or {}).get(
                                     "username") or ""))
    except tg.TelegramError as error:
        _reply(f"⚠ No se pudo vincular: {error}")
        return {"ok": True}
    _reply("✅ <b>Telegram vinculado con Job Agent</b>\n"
           "Recibirás aquí las nuevas ofertas de tus búsquedas.")
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
