"""Notificaciones de ofertas por Telegram (fase 1: solo avisos).

Cada usuario vincula su propio chat (telegram_links/{uid}); el bot
envia ofertas nuevas de SUS busquedas con boton "Ver oferta".
Nunca detiene la busqueda: todo fallo se registra y se continua.

Fase 2 (pendiente): botones callback Postularme/Descartar/Ver
despues — el teclado inline ya deja el hueco (ver build_keyboard).
"""
from __future__ import annotations

import html as _html
import logging
import os as _os
import secrets
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org"


def _env_int(name: str, default: int) -> int:
    try:
        return int((_os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


class TelegramError(Exception):
    """Fallo clasificado: no_token|invalid_token|blocked|invalid_chat|
    api_error|no_link|already_linked|expired|used|disabled."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def enabled() -> bool:
    return bool((_os.getenv("TELEGRAM_BOT_TOKEN") or "").strip())


def _token() -> str:
    token = (_os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise TelegramError("disabled", "Bot de Telegram no configurado.")
    return token


def _api(method: str, payload: dict, timeout: int = 20) -> dict:
    """Llama a Bot API. Devuelve result o lanza TelegramError."""
    import httpx

    try:
        response = httpx.post(f"{_API}/bot{_token()}/{method}",
                              json=payload, timeout=timeout)
    except Exception as error:  # noqa: BLE001
        raise TelegramError("api_error", f"Red Telegram fallo: {error}")
    try:
        data = response.json()
    except ValueError:
        raise TelegramError("api_error",
                            f"Respuesta no JSON ({response.status_code})")
    if response.status_code == 200 and data.get("ok"):
        return data.get("result") or {}
    description = str(data.get("description") or "")
    lowered = description.lower()
    if response.status_code in (401, 404) or "unauthorized" in lowered:
        raise TelegramError("invalid_token",
                            "Token del bot invalido (revisalo en Render).")
    if "blocked" in lowered or "deactivated" in lowered:
        raise TelegramError("blocked", "El usuario bloqueo al bot.")
    if "chat not found" in lowered or "chat_id" in lowered \
            or response.status_code == 400:
        raise TelegramError("invalid_chat",
                            f"Chat invalido: {description[:150]}")
    raise TelegramError("api_error",
                        f"Telegram API ({response.status_code}): "
                        f"{description[:150]}")


def bot_username() -> str:
    """Usuario del bot sin @ (env o getMe). Vacio si no resolvible."""
    configured = (_os.getenv("TELEGRAM_BOT_USERNAME") or "").strip().lstrip(
        "@")
    if configured:
        return configured
    if not enabled():
        return ""
    try:
        me = _api("getMe", {}, timeout=15)
        username = str(me.get("username") or "").strip()
        return username
    except TelegramError as error:
        logger.warning("getMe fallo: %s", error)
        return ""


# ---------------------------------------------------------------------------
# Persistencia (dual SQLite/Firestore, mismo patron que pdf_config)
# ---------------------------------------------------------------------------

def _get_link(db, uid: str) -> dict | None:
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        snap = db.collection("telegram_links").document(str(uid)).get()
        if not snap.exists:
            return None
        return dict(snap.to_dict() or {})
    from app.database.models import TelegramLink

    row = db.query(TelegramLink).filter(
        TelegramLink.uid == str(uid)).first()
    if row is None:
        return None
    return {
        "chat_id": row.chat_id,
        "username": row.username,
        "linked_at": row.linked_at.isoformat()
        if row.linked_at else None,
        "link_code": row.link_code,
        "code_created_at": row.code_created_at.isoformat()
        if row.code_created_at else None,
        "code_used": bool(row.code_used),
        "invalid": bool(row.invalid),
        "last_error": row.last_error or "",
    }


def _save_link(db, uid: str, fields: dict) -> None:
    from app.database.firestore_client import is_firestore

    now = datetime.utcnow()
    if is_firestore(db):
        from app.database import firestore_repo as _fs

        ref = db.collection("telegram_links").document(str(uid))
        snap = ref.get()
        current = dict(snap.to_dict() or {}) if snap.exists else {}
        merged = {**current, **fields, "updated_at": _fs.utcnow_naive()}
        ref.set(merged, merge=True)
        return
    from app.database.models import TelegramLink

    row = db.query(TelegramLink).filter(
        TelegramLink.uid == str(uid)).first()
    if row is None:
        row = TelegramLink(uid=str(uid))
        db.add(row)
    for key in ("chat_id", "username", "linked_at", "link_code",
                "code_created_at", "code_used", "invalid", "last_error"):
        if key in fields:
            setattr(row, key, fields[key])
    row.updated_at = now
    db.commit()


def _find_by_code(db, code: str) -> tuple[str | None, dict | None]:
    """(uid, link) con ese codigo o (None, None)."""
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        for snap in db.collection("telegram_links").where(
                "link_code", "==", code).stream():
            return snap.id, dict(snap.to_dict() or {})
        return None, None
    from app.database.models import TelegramLink

    row = db.query(TelegramLink).filter(
        TelegramLink.link_code == code).first()
    if row is None:
        return None, None
    return row.uid, {
        "code_created_at": row.code_created_at.isoformat()
        if row.code_created_at else None,
        "code_used": bool(row.code_used),
    }


def _chat_linked_to_other(db, chat_id: str, uid: str) -> bool:
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        for snap in db.collection("telegram_links").where(
                "chat_id", "==", str(chat_id)).stream():
            if snap.id != str(uid) and (snap.to_dict() or {}).get("chat_id"):
                return True
        return False
    from app.database.models import TelegramLink

    row = db.query(TelegramLink).filter(
        TelegramLink.chat_id == str(chat_id)).first()
    return row is not None and row.uid != str(uid)


def was_sent(db, uid: str, job_id) -> bool:
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        snap = db.collection("users").document(str(uid)).collection(
            "telegram_sent").document(str(job_id)).get()
        return snap.exists
    from app.database.models import TelegramSent

    return db.query(TelegramSent).filter(
        TelegramSent.uid == str(uid),
        TelegramSent.job_id == str(job_id)).first() is not None


def mark_sent(db, uid: str, job_id, message_id: int | None) -> None:
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as _fs

        db.collection("users").document(str(uid)).collection(
            "telegram_sent").document(str(job_id)).set(
                {"sent_at": _fs.utcnow_naive(),
                 "message_id": message_id})
        return
    from app.database.models import TelegramSent

    row = TelegramSent(uid=str(uid), job_id=str(job_id),
                       sent_at=datetime.utcnow(),
                       message_id=message_id)
    db.merge(row)
    db.commit()


# ---------------------------------------------------------------------------
# Vinculacion
# ---------------------------------------------------------------------------

def start_link(db, uid: str) -> dict:
    """Genera codigo temporal + deep link para el usuario autenticado."""
    if not enabled():
        raise TelegramError("disabled", "Bot de Telegram no configurado.")
    username = bot_username()
    if not username:
        raise TelegramError("api_error",
                            "No se pudo resolver el usuario del bot "
                            "(revisa el token).")
    code = secrets.token_urlsafe(9)
    _save_link(db, uid, {
        "link_code": code,
        "code_created_at": datetime.utcnow(),
        "code_used": 0,
    })
    ttl = _env_int("TELEGRAM_LINK_TTL_MINUTES", 15)
    logger.warning("tg-start uid=%s code=%s... expira=%s deep_link host=t.me",
                   str(uid)[:6], code[:4],
                   (datetime.utcnow() + timedelta(minutes=ttl)).isoformat(
                       timespec="seconds"))
    return {
        "code": code,
        "deep_link": f"https://t.me/{username}?start={code}",
        "bot_username": username,
        "expires_in_minutes": ttl,
    }


def confirm_link(db, code: str, chat_id, username: str | None) -> dict:
    """Vincula el chat al uid dueño del codigo (lo llama el webhook)."""
    from app.database.firestore_client import as_naive_utc

    clean = str(code or "").strip()
    owner_uid, link = _find_by_code(db, clean)
    logger.warning("tg-confirm code=%s... len=%d found=%s",
                   clean[:4], len(clean), bool(owner_uid))
    if not owner_uid or not link:
        logger.warning("tg-confirm resultado=desconocido")
        raise TelegramError("expired", "Codigo desconocido o vencido.")
    if link.get("code_used"):
        logger.warning("tg-confirm resultado=usado uid=%s",
                       str(owner_uid)[:6])
        raise TelegramError("used", "Codigo ya utilizado.")
    moment = as_naive_utc(link.get("code_created_at"))
    if moment is None:
        logger.warning("tg-confirm resultado=fecha-ilegible")
        raise TelegramError("expired", "Codigo vencido.")
    age = (datetime.utcnow() - moment).total_seconds()
    ttl = _env_int("TELEGRAM_LINK_TTL_MINUTES", 15)
    if age > ttl * 60:
        logger.warning("tg-confirm resultado=expirado age_s=%d ttl_min=%d",
                       int(age), ttl)
        raise TelegramError("expired", "Codigo vencido.")
    if _chat_linked_to_other(db, chat_id, owner_uid):
        logger.warning("tg-confirm resultado=otro-dueno uid=%s",
                       str(owner_uid)[:6])
        raise TelegramError(
            "already_linked",
            "Este Telegram ya esta vinculado a otra cuenta.")
    _save_link(db, owner_uid, {
        "chat_id": str(chat_id),
        "username": (username or "").lstrip("@")[:128],
        "linked_at": datetime.utcnow(),
        "code_used": 1,
        "invalid": 0,
        "last_error": "",
    })
    logger.warning("tg-confirm resultado=vinculado uid=%s chat=%s",
                   str(owner_uid)[:6], chat_id)
    return {"uid": owner_uid}


def get_status(db, uid: str) -> dict:
    """Estado + validez en vivo (sin mutar nada)."""
    link = _get_link(db, uid) or {}
    chat_id = link.get("chat_id")
    if not chat_id:
        return {"connected": False, "username": None, "linked_at": None,
                "valid": False, "bot_username": bot_username() or None}
    try:
        _api("getChat", {"chat_id": chat_id}, timeout=15)
        valid, error = True, ""
    except TelegramError as err:
        valid, error = False, str(err)[:200]
    return {
        "connected": True,
        "username": link.get("username"),
        "linked_at": link.get("linked_at"),
        "valid": valid,
        "error": error,
        "bot_username": bot_username() or None,
    }


def unlink(db, uid: str) -> bool:
    """Desconecta (borra chat_id, conserva fila)."""
    link = _get_link(db, uid)
    if not link or not link.get("chat_id"):
        return False
    _save_link(db, uid, {"chat_id": None, "username": None,
                         "linked_at": None, "invalid": 0,
                         "last_error": ""})
    return True


def _mark_invalid(db, uid: str, message: str) -> None:
    try:
        _save_link(db, uid, {"invalid": 1, "last_error": message[:200]})
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Mensajes
# ---------------------------------------------------------------------------

def _esc(text) -> str:
    return _html.escape(str(text or ""), quote=False).strip()


def build_keyboard(url: str) -> dict:
    buttons = [[{"text": "Ver oferta", "url": url}]]
    # Fase 2: aqui iran callback_data Postularme/Descartar/Ver despues.
    return {"inline_keyboard": buttons}


def build_job_message(job) -> tuple[str, dict]:
    """(texto HTML, reply_markup) desde un Record/dict de oferta."""
    if isinstance(job, dict):
        get = job.get
    else:
        def get(key, default=""):
            return getattr(job, key, default) or default
    title = _esc(get("title")) or "Oferta"
    lines = [f"<b>{title}</b>"]
    company = _esc(get("company"))
    if company:
        lines.append(f"🏢 {company}")
    meta = " · ".join(p for p in (
        _esc(get("location")), _esc(get("modality"))) if p)
    if meta:
        lines.append(f"📍 {meta}")
    salary = _esc(get("salary"))
    if salary:
        lines.append(f"💰 {salary}")
    score = get("match_score")
    try:
        if score is not None and float(score) > 0:
            lines.append(f"🎯 Match: {int(float(score))}%")
    except (TypeError, ValueError):
        pass
    desc = _esc(get("description"))
    if desc:
        short = desc if len(desc) <= 300 else desc[:300].rstrip() + "…"
        lines.append("")
        lines.append(short)
    url = str(get("url") or "").strip()
    return "\n".join(lines)[:4000], build_keyboard(url)


def send_message(chat_id, text: str, reply_markup: dict | None = None,
                 timeout: int = 20) -> int | None:
    """Envia y devuelve message_id. Clasifica errores de Telegram."""
    payload = {"chat_id": str(chat_id), "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    result = _api("sendMessage", payload, timeout=timeout)
    message_id = result.get("message_id")
    try:
        return int(message_id) if message_id is not None else None
    except (TypeError, ValueError):
        return None


def send_test(db, uid: str) -> dict:
    """Mensaje de prueba (tambien valida la conexion)."""
    link = _get_link(db, uid) or {}
    chat_id = link.get("chat_id")
    if not chat_id:
        raise TelegramError("no_link", "Telegram no conectado.")
    try:
        message_id = send_message(
            chat_id, "🔔 <b>Job Agent conectado</b>\n"
                     "Recibiras aqui las nuevas ofertas de tus busquedas.")
    except TelegramError as error:
        if error.code in ("blocked", "invalid_chat"):
            _mark_invalid(db, uid, str(error))
        raise
    return {"message_id": message_id}


def send_job(db, uid: str, job) -> int | None:
    """Avisa UNA oferta (idempotente). Devuelve message_id o None si ya
    estaba avisada. Lanza TelegramError en fallo real."""
    job_id = job["id"] if isinstance(job, dict) else job.id
    if was_sent(db, uid, job_id):
        return None
    link = _get_link(db, uid) or {}
    chat_id = link.get("chat_id")
    if not chat_id:
        raise TelegramError("no_link", "Telegram no conectado.")
    text, keyboard = build_job_message(job)
    try:
        message_id = send_message(chat_id, text, keyboard)
    except TelegramError as error:
        if error.code in ("blocked", "invalid_chat"):
            _mark_invalid(db, uid, str(error))
        raise
    mark_sent(db, uid, job_id, message_id)
    return message_id


def notify_new_jobs(db, uid: str | None, job_ids: list,
                    email: str | None = None) -> dict:
    """Avisa ofertas nuevas al usuario. NUNCA lanza: devuelve resumen.

    Se llama al final de run_profile (cubre manual + automatico).
    """
    max_per_run = _env_int("TELEGRAM_MAX_PER_RUN", 10)

    summary: dict = {"sent": 0, "skipped": 0, "errors": []}
    if not uid or not enabled():
        return summary
    try:
        link = _get_link(db, uid) or {}
        if not link.get("chat_id") or link.get("invalid"):
            return summary
        pending = [jid for jid in (job_ids or [])
                   if not was_sent(db, uid, jid)]
        if not pending:
            return summary
        from app.services import job_service as jobs

        for job_id in pending[:max(1, max_per_run)]:
            try:
                job = jobs.get_job_by_id(db, job_id)
                if job is None:
                    continue
                if send_job(db, uid, job) is not None:
                    summary["sent"] += 1
                else:
                    summary["skipped"] += 1
            except TelegramError as error:
                # 403/bloqueo corta el lote (reintentarlo es inutil).
                summary["errors"].append(str(error)[:150])
                if error.code in ("blocked", "invalid_chat"):
                    break
            except Exception as error:  # noqa: BLE001
                summary["errors"].append(str(error)[:150])
        left = len(pending) - min(len(pending), max_per_run)
        summary["skipped"] += max(0, left)
    except Exception as error:  # noqa: BLE001
        logger.warning("Telegram notify fallo (no rompe busqueda): %s",
                       error)
        summary["errors"].append(str(error)[:150])
    return summary
