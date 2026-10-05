"""Contrato de contenido para Adaptar-perfil (auditoria de formatos).

El servicio Perfil guarda normalizado (fechas ISO, años numericos,
ids de catalogo) y `adapt.guest` lo convierte a display (strings
legibles). Este modulo es la frontera tipada antes del matching y
el renderer: recibe el perfil display (+pdf_config) y devuelve
COPIAS coercionadas a los tipos exactos que cada consumidor lee,
mas `warnings` con todo lo que se normalizo en el camino.

Reglas:
- Jamas muta lo guardado: solo copias para generar el PDF.
- Jamas inventa: lo irreconocible se vacia y se reporta.
- Fechas: se conservan como string display ('Mar 2025',
  '03/2025', ISO); el renderer ya formatea cada variante.
- years_experience: numero (palabras 'diez' -> 10) o None.
- Listas: siempre list[str] limpias; dicts solo donde el renderer
  los espera (skills_groups, languages).
"""
from __future__ import annotations


def _str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return ""
    return str(value).strip()


def _str_list(value) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in out:
            out.append(text)
    return out


def _years(value):
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "."))
        return number if 0 <= number <= 60 else None
    except (TypeError, ValueError):
        pass
    from app.profile.schema import _words_to_years

    try:
        number = _words_to_years(str(value))
    except Exception:  # noqa: BLE001
        return None
    return number if number is not None and 0 <= number <= 60 else None


def _entry(section: str, raw: dict, warnings: list[str]) -> dict:
    raw = dict(raw or {})
    out = dict(raw)
    if section in ("experience", "education", "projects",
                   "certifications"):
        for key in ("title", "name", "degree", "company",
                    "institution", "description", "period"):
            if key in out:
                out[key] = _str(out.get(key))
        for key in ("technical_skills", "soft_skills", "technologies"):
            if key in out:
                out[key] = _str_list(out.get(key))
        for key in ("start", "end", "start_date", "end_date",
                    "issued", "expiry", "issued_date", "expiry_date"):
            if key in out and out[key] is not None:
                out[key] = _str(out[key])
    if section == "experience":
        out["is_current"] = bool(out.get("is_current"))
    return out


def _language(raw: dict) -> dict:
    raw = dict(raw or {})
    general = _str(raw.get("level"))
    out = {
        "label": _str(raw.get("label") or raw.get("language_label")),
        "academy": _str(raw.get("academy")),
        "level": general,
        "listening": _str(raw.get("listening")) or general,
        "reading": _str(raw.get("reading")) or general,
        "writing": _str(raw.get("writing")) or general,
        "speaking": _str(raw.get("speaking")) or general,
    }
    return out


def coerce_profile(profile: dict) -> tuple[dict, list[str]]:
    """Perfil display -> copia tipada para matcher/selector/renderer."""
    warnings: list[str] = []
    src = dict(profile or {})
    out: dict = {
        "full_name": _str(src.get("full_name")),
        "title": _str(src.get("title")),
        "email": _str(src.get("email")),
        "phone": _str(src.get("phone")),
        "linkedin": _str(src.get("linkedin")),
        "github": _str(src.get("github")),
        "portfolio": _str(src.get("portfolio")),
        "location": _str(src.get("location")),
        "modality": _str(src.get("modality")),
        "summary": _str(src.get("summary")),
        "skills_technical": _str_list(src.get("skills_technical")),
        "skills_soft": _str_list(src.get("skills_soft")),
        "target_roles": _str_list(src.get("target_roles")),
        "languages": [],
        "experiences": [],
        "education": [],
        "projects": [],
        "certifications": [],
        "other_studies": [],
        "other_knowledge": [],
    }
    years_raw = src.get("years_experience")
    out["years_experience"] = _years(years_raw)
    if years_raw not in (None, "") and out["years_experience"] is None:
        warnings.append(
            f"years_experience '{years_raw}' irreconocible: se omite.")

    groups = src.get("skills_groups")
    if isinstance(groups, dict):
        out["skills_groups"] = {str(k): _str_list(v)
                                for k, v in groups.items()}
    else:
        if groups not in (None, "", [], {}):
            warnings.append("skills_groups con forma inesperada: se omite.")
        out["skills_groups"] = {}

    for raw_lang in src.get("languages") or []:
        if isinstance(raw_lang, dict):
            out["languages"].append(_language(raw_lang))
        elif str(raw_lang or "").strip():
            out["languages"].append(_language({"label": raw_lang}))

    for key in ("experiences", "education", "projects",
                "certifications"):
        items = src.get(key)
        if key == "experiences":
            items = src.get("experiences") or src.get("experience") or []
        if not isinstance(items, list):
            warnings.append(f"'{key}' no es lista: se omite.")
            continue
        section_kind = {"experiences": "experience"}.get(key, key)
        for item in items:
            if isinstance(item, dict):
                out[key].append(_entry(section_kind, item, warnings))

    for key in ("other_studies", "other_knowledge"):
        value = src.get(key)
        if isinstance(value, dict):
            out[key] = value
        else:
            out[key] = _str_list(value)
    return out, warnings


_ALLOWED_DATE_FORMATS = ("MMM YYYY", "MM/YYYY", "MM/YY", "MMMM YYYY",
                         "YYYY-MM")
_ALLOWED_FONTS = ("georgia", "times", "arial")
_ALLOWED_SIZES = (10, 11, 12, 14, 16)
_KNOWN_SECTIONS = ("summary", "experience", "education", "projects",
                   "skills", "soft_skills", "languages",
                   "other_studies", "other_knowledge")
_DEFAULT_ORDER = ["summary", "experience", "education", "projects",
                  "skills", "soft_skills", "languages",
                  "other_studies", "other_knowledge"]


def coerce_pdf_config(pdf_config: dict | None) -> tuple[dict, list[str]]:
    """pdf_config crudo -> tipos exactos del renderer (+warnings)."""
    warnings: list[str] = []
    src = dict(pdf_config or {})
    out = dict(src)

    font = _str(src.get("font_family")).lower()
    out["font_family"] = font if font in _ALLOWED_FONTS else "georgia"
    if font and font not in _ALLOWED_FONTS:
        warnings.append(f"font_family '{font}' no soportada: georgia.")

    try:
        size = int(src.get("font_size_pt", 11))
    except (TypeError, ValueError):
        size = 11
        warnings.append("font_size_pt invalido: 11.")
    out["font_size_pt"] = size if size in _ALLOWED_SIZES else 11
    if size not in _ALLOWED_SIZES:
        warnings.append(f"font_size_pt {size} fuera de menu: 11.")

    order = src.get("section_order")
    if isinstance(order, str):
        import json as _json

        try:
            order = _json.loads(order)
        except ValueError:
            order = None
    if not isinstance(order, list):
        if order not in (None, "", []):
            warnings.append("section_order con forma inesperada: defecto.")
        order = list(_DEFAULT_ORDER)
    clean = [s for s in order if s in _KNOWN_SECTIONS]
    if len(clean) != len(order):
        warnings.append("section_order con secciones desconocidas: "
                        "se ignoran.")
    out["section_order"] = clean or list(_DEFAULT_ORDER)

    fmt = _str(src.get("date_format"))
    out["date_format"] = fmt if fmt in _ALLOWED_DATE_FORMATS else "MMM YYYY"
    if fmt and fmt not in _ALLOWED_DATE_FORMATS:
        warnings.append(f"date_format '{fmt}' desconocido: MMM YYYY.")

    for key in ("margin_top_mm", "margin_bottom_mm", "margin_left_mm",
                "margin_right_mm", "section_spacing_pt"):
        default = 25 if key != "section_spacing_pt" else 14
        raw = src.get(key)
        if raw in (None, ""):
            out[key] = default
            continue
        try:
            out[key] = int(raw)
        except (TypeError, ValueError):
            out[key] = default
            warnings.append(f"{key} invalido: {default}.")
    for key in ("show_skill_chips", "compact_mode"):
        out[key] = bool(src.get(key, True if key == "show_skill_chips"
                                else False))
    out["header_style"] = _str(src.get("header_style")) or "classic"
    out["section_divider"] = _str(src.get("section_divider")) or "line"
    out["accent_color"] = _str(src.get("accent_color")) or "#000000"
    return out, warnings
