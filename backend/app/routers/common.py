"""Helpers compartidos (Fase 1: movidos de app/main.py sin cambios)."""
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel

from app.database.models import PDFConfig


def _json_list(value) -> list:
    import json as _json

    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = _json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _auth_account_complete(user: dict | None) -> bool:
    """Cuenta registrada = existe con nombre y telefono (una sola vez)."""
    return bool(user) and bool((user.get("nombre") or "").strip()) \
        and bool((user.get("telefono") or "").strip())


class PDFConfigOut(BaseModel):
    font_family: str
    font_size_pt: int
    section_order: list[str]
    date_format: str
    show_skill_chips: bool
    compact_mode: bool
    header_style: str
    section_divider: str
    margin_top_mm: int
    margin_bottom_mm: int
    margin_left_mm: int
    margin_right_mm: int
    section_spacing_pt: int
    accent_color: str
    max_projects: int = 3
    max_experiences: int = 3
    max_bullets: int = 0
    profile_length: str = "full"
    show_soft_skills: bool = True
    show_courses: bool = True
    show_languages: bool = True
    show_links: bool = True
    max_pages: int = 0
    ai_rewrite_bullets: bool = False

    class Config:
        from_attributes = True


class PDFConfigIn(BaseModel):
    font_family: str | None = None
    font_size_pt: int | None = None
    section_order: list[str] | None = None
    date_format: str | None = None
    show_skill_chips: bool | None = None
    compact_mode: bool | None = None
    header_style: str | None = None
    section_divider: str | None = None
    margin_top_mm: int | None = None
    margin_bottom_mm: int | None = None
    margin_left_mm: int | None = None
    margin_right_mm: int | None = None
    section_spacing_pt: int | None = None
    accent_color: str | None = None
    max_projects: int | None = None
    max_experiences: int | None = None
    max_bullets: int | None = None
    profile_length: str | None = None
    show_soft_skills: bool | None = None
    show_courses: bool | None = None
    show_languages: bool | None = None
    show_links: bool | None = None
    max_pages: int | None = None
    ai_rewrite_bullets: bool | None = None


def _pdf_config_to_out(cfg) -> PDFConfigOut:
    """Acepta fila ORM o dict plano (Fase 2: servicio dual)."""
    import json
    get = (lambda k: cfg.get(k)) if isinstance(cfg, dict) else (
        lambda k: getattr(cfg, k))
    order = get("section_order")
    return PDFConfigOut(
        font_family=get("font_family"),
        font_size_pt=get("font_size_pt"),
        section_order=json.loads(order) if order else [],
        date_format=get("date_format"),
        show_skill_chips=bool(get("show_skill_chips")),
        compact_mode=bool(get("compact_mode")),
        header_style=get("header_style"),
        section_divider=get("section_divider"),
        margin_top_mm=get("margin_top_mm"),
        margin_bottom_mm=get("margin_bottom_mm"),
        margin_left_mm=get("margin_left_mm"),
        margin_right_mm=get("margin_right_mm"),
        section_spacing_pt=get("section_spacing_pt"),
        accent_color=get("accent_color"),
        max_projects=get("max_projects") if get("max_projects")
        is not None else 3,
        max_experiences=get("max_experiences") if get("max_experiences")
        is not None else 3,
        max_bullets=get("max_bullets") if get("max_bullets")
        is not None else 0,
        profile_length=get("profile_length") or "full",
        show_soft_skills=bool(get("show_soft_skills")
                              if get("show_soft_skills") is not None
                              else True),
        show_courses=bool(get("show_courses")
                          if get("show_courses") is not None else True),
        show_languages=bool(get("show_languages")
                            if get("show_languages") is not None else True),
        show_links=bool(get("show_links")
                        if get("show_links") is not None else True),
        max_pages=get("max_pages") if get("max_pages")
        is not None else 0,
        ai_rewrite_bullets=bool(get("ai_rewrite_bullets")
                                if get("ai_rewrite_bullets") is not None
                                else False),
    )


def _profile_identity(request: Request) -> tuple:
    """(uid, email) de la sesion Firebase, o (None, None) sin token.

    Token presente pero invalido -> 401 (no se regala acceso legado).
    Admin sin configurar (503) -> (None, None): modo local historico."""

    raw = request.headers.get("authorization")
    if not raw:
        return None, None
    try:
        from app.auth import verify_bearer_token

        claims = verify_bearer_token(raw)
        return claims.get("uid"), claims.get("email")
    except HTTPException as exc:
        if exc.status_code == 503:
            return None, None
        raise


def _adapt_identity(request: Request | None,
                    token: str | None = None) -> tuple[str | None, str | None]:
    """(uid, email) de la sesion para Adaptar-perfil.

    Invitado = sin token (header ni ?token=) o anonimo sin email: usa
    el demo y comparte la carpeta "guest". Google = uid + email: usa
    solo su perfil y sus archivos. Centraliza la lectura del Bearer
    para que sync/start/status/download usen siempre EL MISMO perfil.

    Fail-closed: un token PRESENTE pero invalido/expirado (401) o un
    backend sin Firebase (503) NUNCA degradan a invitado — se
    propaga el error. Servir el demo como si fuera tuyo es justo la
    fuga que esto evita.
    """
    from fastapi import HTTPException as _HTTPException

    auth_header = (request.headers.get("authorization")
                   if request is not None else None)
    raw = auth_header
    if (not raw or not raw.lower().startswith("bearer ")) and token:
        raw = f"Bearer {token}"
    if not raw or not raw.lower().startswith("bearer "):
        return None, None
    try:
        from app.auth import verify_bearer_token
        claims = verify_bearer_token(raw)
        return claims.get("uid"), claims.get("email")
    except _HTTPException:
        raise
    except Exception as exc:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail=f"No se pudo verificar la sesión: {exc}")


