"""Normalizacion del perfil modular (§15, §16).

Convierte entradas libres a estructura tipada con valores normalizados:
fechas ISO, titulos/ciudades/modalidades por catalogo, skills como
listas. Nunca inventa: lo irreconocible se descarta con advertencia
o se conserva como texto solo donde el esquema lo permite.
"""
from __future__ import annotations

import re
from datetime import date
from datetime import datetime

from app.profile import catalogs
from app.profile.perspectives import normalize_entry as normalize_perspectives


MESES_ES = {
    "ene": 1, "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3,
    "abr": 4, "abril": 4, "may": 5, "mayo": 5, "jun": 6, "junio": 6,
    "jul": 7, "julio": 7, "ago": 8, "agosto": 8, "sep": 9, "septiembre": 9,
    "oct": 10, "octubre": 10, "nov": 11, "noviembre": 11, "dic": 12,
    "diciembre": 12,
}


def normalize_date(value) -> str | None:
    """Fecha -> 'YYYY-MM-DD'. Acepta date/datetime, 'YYYY-MM-DD',
    'YYYY-MM', 'Mar 2025'/'marzo 2025' (es) y 'YYYY' (-> 1 de enero).
    Todo lo demas -> None (jamas strings como 'abril 2022' sueltos)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    match_full = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if match_full:
        year, month, day = map(int, match_full.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    match_month = re.match(r"^(\d{4})-(\d{1,2})$", text)
    if match_month:
        year, month = map(int, match_month.groups())
        try:
            return date(year, month, 1).isoformat()
        except ValueError:
            return None
    match_year = re.match(r"^(\d{4})$", text)
    if match_year:
        return date(int(match_year.group(1)), 1, 1).isoformat()
    match_es = re.match(
        r"^([a-záéíóúñ]+)\s+(\d{4})$", text.lower())
    if match_es:
        month = MESES_ES.get(match_es.group(1))
        if month:
            return date(int(match_es.group(2)), month, 1).isoformat()
    # Lo que produce la capa display y el habla comun: MM/YYYY,
    # DD/MM/YYYY (tambien con guiones). Round-trip seguro.
    match_my = re.match(r"^(\d{1,2})[/-](\d{4})$", text)
    if match_my:
        month, year = int(match_my.group(1)), int(match_my.group(2))
        try:
            return date(year, month, 1).isoformat()
        except ValueError:
            return None
    match_dmy = re.match(
        r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", text)
    if match_dmy:
        day, month, year = map(int, match_dmy.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def _clean_str(value, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _clean_list(value, limit: int = 100) -> list[str]:
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value or [])
    cleaned = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def normalize_personal(raw: dict | None) -> tuple[dict, list[str]]:
    """Devuelve (personal_normalizado, advertencias)."""
    raw = raw or {}
    warnings: list[str] = []
    first = _clean_str(raw.get("first_name"), 100)
    last = _clean_str(raw.get("last_name"), 100)
    full = _clean_str(raw.get("full_name"), 200)
    if not first and not last and full:
        first, last = catalogs.split_spanish_name(full)
    personal = {
        "first_name": first,
        "last_name": last,
        "full_name": f"{first} {last}".strip() or full,
        "email": _clean_str(raw.get("email"), 200),
        "secondary_email": _clean_str(raw.get("secondary_email"), 200),
        "phone": _clean_str(raw.get("phone"), 50),
        "secondary_phone": _clean_str(raw.get("secondary_phone"), 50),
        "linkedin": _clean_str(raw.get("linkedin"), 300),
        "github": _clean_str(raw.get("github"), 300),
        "portfolio": _clean_str(raw.get("portfolio"), 300),
        "address": _clean_str(raw.get("address"), 300),
    }
    title_raw = _clean_str(raw.get("title"), 200)
    title_item = catalogs.norm_title(title_raw)
    if title_raw and not title_item:
        warnings.append(
            f"Titulo profesional '{title_raw}' fuera de catalogo; "
            "usa 'Otro' o elije una opcion."
        )
        personal["title_id"] = None
        personal["title_label"] = title_raw
    else:
        personal["title_id"] = title_item["id"] if title_item else None
        personal["title_label"] = title_item["label"] if title_item else ""
    # Compat: campos planos que consumen matching/CV viejos.
    personal["title"] = personal["title_label"]
    personal["location"] = _clean_str(raw.get("location"), 200)
    return personal, warnings


def _normalize_city(raw) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    if not raw:
        return None, warnings
    if isinstance(raw, dict) and raw.get("id"):
        city = catalogs.norm_city(raw.get("id"))
        if city:
            return {"id": city["id"], "label": city["label"],
                    "country": city["country"]}, warnings
        raw = raw.get("label", "")
    city = catalogs.norm_city(raw)
    if city:
        return {"id": city["id"], "label": city["label"],
                "country": city["country"]}, warnings
    warnings.append(f"Ciudad '{raw}' fuera de catalogo; se guarda el texto.")
    return {"id": "custom", "label": _clean_str(raw, 100),
            "country": None}, warnings


def normalize_entry(section: str, raw: dict | None, index: int = 0) -> tuple[dict, list[str]]:
    """Normaliza una entrada de experience/education/projects/
    certifications segun su seccion. Devuelve (entrada, advertencias)."""
    from app.profile.perspectives import normalize_entry as _norm_persp

    raw = raw or {}
    warnings: list[str] = []
    entry = _norm_persp(raw)
    entry["technical_skills"] = _clean_list(raw.get("technical_skills"))
    entry["soft_skills"] = _clean_list(raw.get("soft_skills"))
    # Compat: conserva texto libre legacy que consumen CV/matching viejos.
    for legacy_key in ("bullets", "achievements", "technologies",
                       "description", "summary", "period", "facts"):
        if raw.get(legacy_key) is not None and legacy_key not in entry:
            entry[legacy_key] = raw.get(legacy_key)

    if section == "experience" or section == "experiences":
        entry["company"] = _clean_str(
            raw.get("company") or raw.get("organization"), 200)
        entry["title"] = _clean_str(
            raw.get("title") or raw.get("role") or raw.get("position"), 200)
        # Acepta tanto start_date/end_date como start/end (compatibilidad)
        start_raw = raw.get("start_date") or raw.get("start")
        end_raw = raw.get("end_date") or raw.get("end")
        entry["start_date"] = normalize_date(start_raw)
        entry["is_current"] = bool(raw.get("is_current"))
        if entry["is_current"]:
            # Actualmente trabaja aqui: end_date = null, jamas fecha ficticia.
            entry["end_date"] = None
        else:
            entry["end_date"] = normalize_date(end_raw)
        entry["modality"] = catalogs.norm_modality(raw.get("modality"))
        if raw.get("modality") and not entry["modality"]:
            warnings.append("Modalidad no reconocida; usa el selector.")
        entry["city"], city_warnings = _normalize_city(raw.get("city"))
        warnings.extend(city_warnings)
        entry["description"] = _clean_str(raw.get("description"), 2000)
        entry["contract_type"] = _clean_str(raw.get("contract_type"), 50) or None
    elif section == "education":
        entry["institution"] = _clean_str(
            raw.get("institution") or raw.get("company"), 200)
        entry["degree"] = _clean_str(
            raw.get("degree") or raw.get("title") or raw.get("program"), 300)
        entry["level"] = catalogs.norm_education_level(raw.get("level"))
        if raw.get("level") and not entry["level"]:
            warnings.append(f"Nivel educativo '{raw.get('level')}' fuera de catalogo.")
        entry["start_date"] = normalize_date(raw.get("start_date"))
        entry["end_date"] = normalize_date(raw.get("end_date"))
        entry["status"] = _clean_str(raw.get("status"), 30) or None
        valid_status = {item["id"] for item in catalogs.ENTRY_STATUS}
        if entry["status"] and entry["status"] not in valid_status:
            warnings.append(f"Estado '{entry['status']}' fuera de catalogo.")
            entry["status"] = None
        entry["description"] = _clean_str(raw.get("description"), 2000)
    elif section == "projects":
        entry["name"] = _clean_str(
            raw.get("name") or raw.get("title"), 200)
        entry["description"] = _clean_str(raw.get("description"), 2000)
        entry["start_date"] = normalize_date(raw.get("start_date"))
        entry["end_date"] = normalize_date(raw.get("end_date"))
        entry["url"] = _clean_str(raw.get("url"), 300)
        entry["repo"] = _clean_str(
            raw.get("repo") or raw.get("repository"), 300)
        entry["technologies"] = _clean_list(raw.get("technologies"))
    elif section == "certifications":
        entry["name"] = _clean_str(
            raw.get("name") or raw.get("title"), 200)
        entry["institution"] = _clean_str(
            raw.get("institution") or raw.get("issuer"), 200)
        entry["issued_date"] = normalize_date(
            raw.get("issued_date") or raw.get("date"))
        entry["expiry_date"] = normalize_date(
            raw.get("expiry_date") or raw.get("expires"))
        entry["credential_id"] = _clean_str(raw.get("credential_id"), 200)
        entry["credential_url"] = _clean_str(raw.get("credential_url"), 300)
        entry["description"] = _clean_str(raw.get("description"), 1000)
    return entry, warnings


def normalize_language(raw: dict | None, index: int = 0) -> tuple[dict, list[str]]:
    raw = raw or {}
    warnings: list[str] = []
    lang = catalogs.norm_language(raw.get("language") or raw.get("id"))
    if raw.get("language") and not lang:
        warnings.append(f"Idioma '{raw.get('language')}' fuera de catalogo.")
    entry = {
        "id": str(raw.get("id") or f"lang{index + 1}"),
        "language": lang["id"] if lang else None,
        "language_label": lang["label"] if lang else _clean_str(raw.get("language"), 50),
        "academy": _clean_str(raw.get("academy") or raw.get("institution"), 200),
    }
    for key in ("level", "listening", "reading", "writing", "speaking"):
        normed = catalogs.norm_language_level(raw.get(key))
        if raw.get(key) and not normed:
            warnings.append(f"Nivel '{raw.get(key)}' invalido en {key}; usa A1-C2/Nativo.")
        entry[key] = normed
    return entry, warnings


def _to_years(value) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip().lower().replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        number = _words_to_years(text)
        if number is None:
            return None
    if number < 0 or number > 60:
        return None
    return number


_NUMBER_WORDS: dict[str, float] = {
    "cero": 0, "uno": 1, "una": 1, "un": 1, "dos": 2,
    "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "medio": 0.5, "media": 0.5, "mitad": 0.5,
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "half": 0.5,
}


def _words_to_years(text: str) -> float | None:
    """'diez' -> 10, 'dos anos y medio' -> 2.5, '3 anos' -> 3.

    Solo palabras numericas sueltas (con 'ano(s)/year(s)/y medio'
    opcionales). Cualquier otra prosa -> None (no se adivina).
    """
    import re as _re
    import unicodedata as _ud

    plain = "".join(
        c for c in _ud.normalize("NFKD", text) if not _ud.combining(c))
    tokens = _re.findall(r"[a-z0-9.]+", plain)
    if not tokens:
        return None
    total: float = 0.0
    seen_number = False
    seen_filler = False
    for token in tokens:
        if token in _NUMBER_WORDS:
            total += _NUMBER_WORDS[token]
            seen_number = True
            continue
        try:
            total += float(token)
            seen_number = True
            continue
        except ValueError:
            pass
        if token in ("anos", "ano", "years", "year", "y", "and", "de"):
            seen_filler = True
            continue
        return None
    if not seen_number:
        return None
    if not seen_filler and len(tokens) > 3:
        return None
    return round(total, 2) if seen_number else None


def parse_salary(value) -> dict:
    """Salario -> {amount, currency, period} best-effort.

    Acepta el formato canonico "2500000 COP mensual", un numero
    suelto ("3500000") o partes estructuradas
    (min_salary_amount/currency/period). Jamas falla: lo irreconocible
    se devuelve como texto en 'raw'.
    """
    out: dict = {"amount": None, "currency": None, "period": None,
                 "raw": ""}
    if value is None:
        return out
    text = str(value).strip()
    out["raw"] = text
    if not text:
        return out
    match = re.match(
        r"^([\d][\d.,]*)\s*([A-Za-z]{3})?\s*(.*)$", text)
    if match:
        digits = re.sub(r"[.,]", "", match.group(1))
        try:
            out["amount"] = int(digits) if digits else None
        except ValueError:
            out["amount"] = None
        out["currency"] = catalogs.norm_salary_currency(
            match.group(2)) if match.group(2) else None
        out["period"] = catalogs.norm_salary_period(
            match.group(3)) if match.group(3).strip() else None
    return out


def format_salary(amount=None, currency=None, period=None,
                  raw: str = "") -> str:
    """Reconstruye el string canonico del salario para guardar."""
    parts = []
    if amount not in (None, ""):
        parts.append(str(amount).strip())
    if currency:
        parts.append(str(currency).strip().upper())
    if period:
        period_item = catalogs.norm_salary_period(period)
        parts.append(period_item if period_item else str(period).strip())
    if parts:
        return " ".join(parts)
    return (raw or "").strip()


def normalize_flat_profile(data: dict | None) -> tuple[dict, list[str]]:
    """Normaliza el perfil plano (/profile) contra catalogos.

    Colapsa variantes ("hibrido" -> "HYBRID", "analista datos" ->
    "Analista de Datos") sin borrar nada: lo irreconocible se conserva
    como texto y se reporta en advertencias. Devuelve
    (perfil_normalizado, advertencias).
    """
    data = dict(data or {})
    warnings: list[str] = []

    modality_raw = str(data.get("modality") or "").strip()
    if modality_raw:
        modality = catalogs.norm_modality(modality_raw)
        if modality:
            data["modality"] = modality
        else:
            warnings.append(
                f"Modalidad '{modality_raw}' fuera de catalogo; "
                "usa el selector (Presencial/Híbrido/Remoto).")

    level_raw = str(data.get("experience_level") or "").strip()
    if level_raw:
        level = catalogs.norm_seniority(level_raw)
        if level:
            data["experience_level"] = level["id"]
        else:
            warnings.append(
                f"Nivel '{level_raw}' fuera de catalogo; "
                "usa el selector de nivel.")

    roles = _clean_list(data.get("target_roles"), 20)
    normalized_roles = []
    for role in roles:
        item = catalogs.norm_title(role)
        normalized_roles.append(item["label"] if item else role)
        if not item:
            warnings.append(
                f"Cargo objetivo '{role}' fuera de catalogo; "
                "elige una opcion para mejor matching.")
    data["target_roles"] = normalized_roles

    sectors = _clean_list(data.get("sectors"), 20)
    normalized_sectors = []
    for sector in sectors:
        item = catalogs.norm_sector(sector)
        normalized_sectors.append(item["label"] if item else sector)
        if not item:
            warnings.append(
                f"Sector '{sector}' fuera de catalogo; "
                "elige una opcion.")
    data["sectors"] = normalized_sectors

    # Skills: dedupe insensible a mayusculas/tildes ("Power BI" y
    # "power bi" son la misma skill y solo inflan el matching).
    skills = _clean_list(data.get("skills"), 100)
    seen_skills: set[str] = set()
    unique_skills: list[str] = []
    for skill in skills:
        key = catalogs.norm_text(skill)
        if key and key not in seen_skills:
            seen_skills.add(key)
            unique_skills.append(skill)
    data["skills"] = unique_skills

    for key in ("location", "preferred_location"):
        loc_raw = str(data.get(key) or "").strip()
        if loc_raw:
            city = catalogs.norm_city(loc_raw)
            if city:
                data[key] = city["label"]
            else:
                warnings.append(
                    f"Ubicación '{loc_raw}' fuera de catalogo; "
                    "elige una ciudad de la lista.")

    salary_parts = parse_salary(data.get("min_salary"))
    structured_amount = data.get("min_salary_amount")
    structured_currency = data.get("min_salary_currency")
    structured_period = data.get("min_salary_period")
    if (structured_amount not in (None, "")
            or structured_currency or structured_period):
        amount = structured_amount if structured_amount not in (
            None, "") else salary_parts["amount"]
        currency = (
            catalogs.norm_salary_currency(structured_currency)
            if structured_currency
            else salary_parts["currency"])
        period = (structured_period if structured_period
                  else salary_parts["period"])
        data["min_salary"] = format_salary(
            amount, currency, period, salary_parts["raw"])
        if structured_currency and not currency:
            warnings.append(
                f"Moneda '{structured_currency}' no reconocida; "
                "usa el selector (COP/USD/…).")
        if structured_period and not catalogs.norm_salary_period(
                structured_period):
            warnings.append(
                f"Periodicidad '{structured_period}' no reconocida.")
    for extra in ("min_salary_amount", "min_salary_currency",
                  "min_salary_period"):
        data.pop(extra, None)

    return data, warnings


def normalize_rich_profile(data: dict | None) -> tuple[dict, list[str]]:
    """Normaliza el documento completo del perfil modular."""
    from app.profile.perspectives import SECTIONS

    data = data or {}
    warnings: list[str] = []
    personal, personal_warnings = normalize_personal(data.get("personal"))
    warnings.extend(personal_warnings)
    normalized: dict = {
        "personal": personal,
        "professional_summary": _clean_str(
            data.get("professional_summary"), 2000),
        "years_experience": _to_years(data.get("years_experience")),
        "technical_skills": _clean_list(data.get("technical_skills")),
        "soft_skills": _clean_list(data.get("soft_skills")),
        "languages": [],
        "target_roles": _clean_list(data.get("target_roles"), 20),
    }
    if data.get("years_experience") not in (None, "") and normalized["years_experience"] is None:
        warnings.append("years_experience debe ser numerico (ej. 2 o 2.5).")
    for index, raw in enumerate(data.get("languages") or []):
        if isinstance(raw, str):
            # Formato viejo (texto libre) -> estructurado best-effort.
            raw = {"language": raw}
        if not isinstance(raw, dict):
            continue
        entry, entry_warnings = normalize_language(raw, index)
        normalized["languages"].append(entry)
        warnings.extend(entry_warnings)
    for section in SECTIONS:
        items = data.get(section)
        if not isinstance(items, list):
            normalized[section] = []
            continue
        normalized[section] = []
        for index, raw in enumerate(items):
            if isinstance(raw, str):
                # Formato viejo (texto libre) -> entrada minima.
                raw = {"name": raw} if section in (
                    "projects", "certifications") else {"title": raw}
            if not isinstance(raw, dict):
                continue
            entry, entry_warnings = normalize_entry(section, raw, index)
            normalized[section].append(entry)
            warnings.extend(entry_warnings)
    # Compat hacia atras: skills agrupados que consumen CV/matching viejos.
    normalized["skills"] = data.get("skills") if isinstance(
        data.get("skills"), dict) else {}
    # Passthrough: no borrar claves que el esquema no conoce.
    for key, value in data.items():
        if key not in normalized:
            normalized[key] = value
    return normalized, warnings
