"""Fuente de perfil para el adaptador de CV (FASE 1 y FASE 16).

`get_profile_for_cv()` devuelve SIEMPRE el ficticio de invitado en
esta fase. `user_id` existe solo como interfaz: cuando se conecten
perfiles reales, este modulo leera Firebase/Firestore segun sesion y
el resto del sistema no cambia.
"""
from __future__ import annotations

from app.services import job_service as jobs

GUEST_USER_ID = None  # Fase 1: sin sesion, siempre invitado.


def _label(items: list[dict], value: str | None, fallback: str = "") -> str:
    for item in items or []:
        if item.get("id") == value:
            return item.get("label") or fallback
    return str(value or fallback)


def _display_date(iso: str | None, day: bool = False) -> str:
    """ISO '2025-03-01' -> '03/2025'; con day=True '15/07/2026'.

    Tolera valores ya-display ('Mar 2025', '2021', 'Actualidad'):
    los devuelve tal cual en vez de vaciarlos."""
    import re as _re

    if not iso:
        return ""
    text = str(iso).strip()
    if _re.match(r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2} \d{4}$", text):
        return text
    if _re.match(r"^\d{4}$", text):
        return text
    if text.lower() == "actualidad":
        return "Actualidad"
    parts = text.split("-")
    if len(parts) < 2:
        return text
    if day and len(parts) >= 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return f"{parts[1]}/{parts[0]}"


def to_display_profile(flat: dict, rich: dict) -> dict:
    """Normalizado (ids) -> presentacion (etiquetas legibles)."""
    from app.profile import catalogs

    personal = dict(rich.get("personal") or {})
    city = personal.get("city") if isinstance(
        personal.get("city"), dict) else None

    def entry_display(section: str, raw: dict) -> dict:
        raw = dict(raw)
        out = dict(raw)
        if section == "experience":
            out["modality"] = _label(
                catalogs.MODALITIES, raw.get("modality"),
                str(raw.get("modality") or ""))
            out["city"] = (raw.get("city") or {}).get("label", "") \
                if isinstance(raw.get("city"), dict) \
                else str(raw.get("city") or "")
            out["contract"] = _label(
                catalogs.CONTRACT_TYPES, raw.get("contract_type"),
                str(raw.get("contract_type") or ""))
            out["start"] = _display_date(raw.get("start_date"))
            out["end"] = "" if raw.get("is_current") else _display_date(
                raw.get("end_date"))
        elif section == "education":
            out["level"] = _label(
                catalogs.EDUCATION_LEVELS, raw.get("level"),
                str(raw.get("level") or ""))
            out["status"] = _label(
                catalogs.ENTRY_STATUS, raw.get("status"),
                str(raw.get("status") or ""))
            out["start"] = _display_date(raw.get("start_date"))
            out["end"] = _display_date(raw.get("end_date"))
        elif section == "projects":
            out["start"] = _display_date(raw.get("start_date"))
            out["end"] = _display_date(raw.get("end_date"))
        elif section == "certifications":
            out["issued"] = _display_date(raw.get("issued_date"), day=True)
            out["expiry"] = _display_date(raw.get("expiry_date"), day=True)
        return out

    languages = []
    for lang in rich.get("languages") or []:
        if not isinstance(lang, dict):
            continue
        languages.append({
            "label": lang.get("language_label") or _label(
                catalogs.LANGUAGES, lang.get("language"), ""),
            "academy": lang.get("academy") or "",
            "level": lang.get("level") or "",
            "listening": lang.get("listening") or "",
            "reading": lang.get("reading") or "",
            "writing": lang.get("writing") or "",
            "speaking": lang.get("speaking") or "",
        })

    return {
        "full_name": personal.get("full_name") or flat.get("full_name", ""),
        "title": (personal.get("title_label")
                  or personal.get("title")
                  or flat.get("title", "")),
        "email": personal.get("email") or "",
        "phone": personal.get("phone") or "",
        "linkedin": personal.get("linkedin") or flat.get("linkedin", ""),
        "github": personal.get("github") or flat.get("github", ""),
        "portfolio": personal.get("portfolio") or flat.get("portfolio", ""),
        "location": (personal.get("location")
                     or flat.get("location", "")),
        "modality": flat.get("modality", ""),
        "summary": rich.get("professional_summary") or "",
        "years_experience": rich.get("years_experience"),
        "skills_technical": list(rich.get("technical_skills") or []),
        "skills_soft": list(rich.get("skills_soft") or rich.get("soft_skills") or []),
        "skills_groups": dict(rich.get("skills_groups") or rich.get("skills") or {}),
        "target_roles": list(rich.get("target_roles") or []),
        "languages": languages,
        "experiences": [entry_display("experience", e)
                        for e in (rich.get("experiences") or rich.get("experience") or [])],
        "education": [entry_display("education", e)
                      for e in rich.get("education") or []],
        "projects": [entry_display("projects", e)
                     for e in rich.get("projects") or []],
        "certifications": [entry_display("certifications", e)
                           for e in rich.get("certifications") or []],
        # Sin fallback a datos demo: usar arrays vacíos si no hay datos
        "other_knowledge": rich.get("other_knowledge") or [],
        "other_studies": rich.get("other_studies") or [],
    }


def get_profile_for_cv(db=None, user_id=None) -> dict:
    """Perfil para adaptar el CV.
    
    - Si user_id es None o "__guest__": usa datos demo de invitado
    - Si hay user_id real: usa el perfil del usuario autenticado (sin fallback a demo)
    """
    from app.services import job_service as jobs

    # Determinar qué perfil usar
    if user_id and user_id != "__guest__":
        # Usuario autenticado: usar su perfil real (sin fallback a demo)
        flat = jobs.get_profile_for(db, user_id, "")
        rich = jobs.get_rich_profile_for(db, user_id, "")
        # Para usuarios autenticados, asegurar que los campos opcionales sean arrays vacíos si no existen
        # para evitar fallback a datos demo en to_display_profile
        rich.setdefault("other_knowledge", [])
        rich.setdefault("other_studies", [])
        rich.setdefault("certifications", [])
    else:
        # Invitado: usar datos demo
        flat = jobs.get_profile_for(db, "__guest__", "")
        rich = jobs.get_rich_profile_for(db, "__guest__", "")
    
    flat = {k: v for k, v in flat.items() if not k.startswith("_")}
    return to_display_profile(flat, rich)


def profile_is_empty(profile: dict) -> bool:
    """True si no hay con que trabajar (dispara PROFILE_NOT_FOUND)."""
    if (profile.get("full_name") or "").strip():
        return False
    skills = list(profile.get("skills_technical") or []) + list(
        profile.get("skills_soft") or [])
    return not any(str(s).strip() for s in skills)
