"""PDF-config agnostica al motor (Fase 2).

Los endpoints y adapt/service.py usaban `db.query(PDFConfig)` directo:
solo funcionaba en SQLite y rompia en Firestore (prod). Este modulo
es el unico punto de acceso: despacha por `is_firestore(db)` igual
que `user_service`, con identica semantica en ambos motores:

- get-or-create con defaults del modelo
- validacion font_size_pt en {10,11,12,14,16} (ValueError -> 400)
- margenes APA 25mm y accent negro siempre forzados
- section_order persistido como JSON string en ambos motores
- devuelve dict plano (no ORM) para que el renderer no dependa de SQL
"""
from __future__ import annotations

import json
from datetime import datetime

from app.adapt.defaults import ALLOWED_SIZES

ALLOWED_FONT_SIZES = ALLOWED_SIZES

DEFAULTS = {
    "font_family": "georgia",
    "font_size_pt": 11,
    "section_order": (
        '["summary", "experience", "education", "projects", '
        '"skills", "languages", "other_studies", "other_knowledge"]'
    ),
    "date_format": "MM/YYYY",
    "show_skill_chips": 1,
    "compact_mode": 0,
    "header_style": "classic",
    "section_divider": "line",
    "margin_top_mm": 25,
    "margin_bottom_mm": 25,
    "margin_left_mm": 25,
    "margin_right_mm": 25,
    "section_spacing_pt": 14,
    "accent_color": "#000000",
    "max_projects": 3,
    "max_experiences": 3,
    "max_bullets": 0,
    "profile_length": "full",
    "show_soft_skills": 1,
    "show_courses": 1,
    "show_languages": 1,
    "show_links": 1,
    "max_pages": 0,
    "ai_rewrite_bullets": 0,
}


def _orm_to_dict(row) -> dict:
    return {
        "uid": row.uid,
        "font_family": row.font_family,
        "font_size_pt": row.font_size_pt,
        "section_order": row.section_order,
        "date_format": row.date_format,
        "show_skill_chips": row.show_skill_chips,
        "compact_mode": row.compact_mode,
        "header_style": row.header_style,
        "section_divider": row.section_divider,
        "margin_top_mm": row.margin_top_mm,
        "margin_bottom_mm": row.margin_bottom_mm,
        "margin_left_mm": row.margin_left_mm,
        "margin_right_mm": row.margin_right_mm,
        "section_spacing_pt": row.section_spacing_pt,
        "accent_color": row.accent_color,
        "max_projects": row.max_projects,
        "max_experiences": row.max_experiences,
        "max_bullets": row.max_bullets,
        "profile_length": row.profile_length,
        "show_soft_skills": row.show_soft_skills,
        "show_courses": row.show_courses,
        "show_languages": row.show_languages,
        "show_links": row.show_links,
        "max_pages": row.max_pages,
        "ai_rewrite_bullets": row.ai_rewrite_bullets,
    }


def _apply_fields(current: dict, fields: dict) -> dict:
    """Valida y mezcla campos sobre los actuales. Lanza ValueError 400."""
    out = dict(current)
    if fields.get("font_family") is not None:
        out["font_family"] = fields["font_family"]
    if fields.get("font_size_pt") is not None:
        if fields["font_size_pt"] not in ALLOWED_FONT_SIZES:
            raise ValueError(
                "font_size_pt debe ser uno de: 10, 11, 12, 14, 16."
            )
        out["font_size_pt"] = fields["font_size_pt"]
    if fields.get("section_order") is not None:
        order = fields["section_order"]
        out["section_order"] = (
            json.dumps(order) if isinstance(order, list) else order
        )
    for key in ("date_format", "header_style", "section_divider",
                "section_spacing_pt"):
        if fields.get(key) is not None:
            out[key] = fields[key]
    if fields.get("show_skill_chips") is not None:
        out["show_skill_chips"] = 1 if fields["show_skill_chips"] else 0
    if fields.get("compact_mode") is not None:
        out["compact_mode"] = 1 if fields["compact_mode"] else 0
    # Margenes APA y negro: siempre fijos, se ignora lo enviado.
    out["margin_top_mm"] = 25
    out["margin_bottom_mm"] = 25
    out["margin_left_mm"] = 25
    out["margin_right_mm"] = 25
    out["accent_color"] = "#000000"
    for key in ("max_projects", "max_experiences", "max_bullets",
                "max_pages"):
        if fields.get(key) is not None:
            try:
                value = int(fields[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} debe ser entero.")
            if value < 0:
                raise ValueError(f"{key} no puede ser negativo.")
            out[key] = value
    if fields.get("profile_length") is not None:
        if fields["profile_length"] not in ("short", "medium", "full"):
            raise ValueError(
                "profile_length debe ser short|medium|full.")
        out["profile_length"] = fields["profile_length"]
    for key in ("show_soft_skills", "show_courses", "show_languages",
                "show_links", "ai_rewrite_bullets"):
        if fields.get(key) is not None:
            out[key] = 1 if fields[key] else 0
    return out


def get_pdf_config(db, uid: str) -> dict:
    """Get-or-create. Nunca None."""
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as fs

        current = fs.get_pdf_config(db, uid)
        if current is None:
            return fs.save_pdf_config(
                db, uid, {"uid": uid, **DEFAULTS,
                          "updated_at": datetime.utcnow()})
        return current
    from app.database.models import PDFConfig

    row = db.query(PDFConfig).filter(PDFConfig.uid == uid).first()
    if row is None:
        row = PDFConfig(uid=uid)
        db.add(row)
        db.commit()
        db.refresh(row)
    return _orm_to_dict(row)


def update_pdf_config(db, uid: str, fields: dict) -> dict:
    """Aplica PATCH parcial con validacion. Lanza ValueError si 400."""
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as fs

        current = fs.get_pdf_config(db, uid)
        if current is None:
            current = {"uid": uid, **DEFAULTS}
        merged = _apply_fields(current, fields or {})
        merged["uid"] = uid
        merged["updated_at"] = datetime.utcnow()
        return fs.save_pdf_config(db, uid, merged)
    from app.database.models import PDFConfig

    row = db.query(PDFConfig).filter(PDFConfig.uid == uid).first()
    if row is None:
        row = PDFConfig(uid=uid)
        db.add(row)
    merged = _apply_fields(_orm_to_dict(row), fields or {})
    for key, value in merged.items():
        if key != "uid":
            setattr(row, key, value)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _orm_to_dict(row)


def reset_pdf_config(db, uid: str) -> dict:
    """Borra y recrea con defaults."""
    from app.database.firestore_client import is_firestore

    if is_firestore(db):
        from app.database import firestore_repo as fs

        fs.delete_pdf_config(db, uid)
        return fs.save_pdf_config(
            db, uid, {"uid": uid, **DEFAULTS,
                      "updated_at": datetime.utcnow()})
    from app.database.models import PDFConfig

    row = db.query(PDFConfig).filter(PDFConfig.uid == uid).first()
    if row is not None:
        db.delete(row)
        db.commit()
    row = PDFConfig(uid=uid)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _orm_to_dict(row)


def get_pdf_config_for_renderer(db, uid: str | None) -> dict:
    """Config lista para html_renderer.render_cv_html.

    Sin uid o sin fila -> {} (renderer usa sus defaults). Nunca lanza:
    si la BD falla, devuelve {} para no romper la generacion del PDF.
    """
    if not uid:
        return {}
    try:
        cfg = get_pdf_config(db, uid)
    except Exception:  # noqa: BLE001
        return {}
    try:
        order = json.loads(cfg["section_order"]) \
            if cfg.get("section_order") else []
    except (ValueError, TypeError):
        order = []
    return {
        "font_family": cfg.get("font_family"),
        "font_size_pt": cfg.get("font_size_pt"),
        "section_order": order,
        "date_format": cfg.get("date_format"),
        "show_skill_chips": bool(cfg.get("show_skill_chips")),
        "compact_mode": bool(cfg.get("compact_mode")),
        "header_style": cfg.get("header_style"),
        "section_divider": cfg.get("section_divider"),
        "margin_top_mm": cfg.get("margin_top_mm"),
        "margin_bottom_mm": cfg.get("margin_bottom_mm"),
        "margin_left_mm": cfg.get("margin_left_mm"),
        "margin_right_mm": cfg.get("margin_right_mm"),
        "section_spacing_pt": cfg.get("section_spacing_pt"),
        "accent_color": cfg.get("accent_color"),
        "max_projects": cfg.get("max_projects", 3),
        "max_experiences": cfg.get("max_experiences", 3),
        "max_bullets": cfg.get("max_bullets", 0),
        "profile_length": cfg.get("profile_length") or "full",
        "show_soft_skills": bool(cfg.get("show_soft_skills", True)),
        "show_courses": bool(cfg.get("show_courses", True)),
        "show_languages": bool(cfg.get("show_languages", True)),
        "show_links": bool(cfg.get("show_links", True)),
        "max_pages": cfg.get("max_pages", 0),
        "ai_rewrite_bullets": bool(cfg.get("ai_rewrite_bullets", False)),
    }
