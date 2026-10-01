"""Catalogos normalizados del perfil (§15).

Un solo lugar define los valores permitidos para campos que afectan el
matching. La UI los consume via GET /catalogs (misma fuente, sin duplicar).
Regla: jamas guardar variantes ("Data Analyst" vs "data analyst") — se
guarda el `id` normalizado y se muestra el `label`.
"""
from __future__ import annotations

import re
import unicodedata


def norm_text(value: str | None) -> str:
    """Minusculas, sin tildes, espacios simples. Base de toda comparacion."""
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


def _by_norm(items: list[dict]) -> dict[str, dict]:
    return {norm_text(item["label"]): item for item in items}


PROFESSIONAL_TITLES: list[dict] = [
    {"id": "software_engineer", "label": "Ingeniero de Software"},
    {"id": "systems_engineer", "label": "Ingeniero de Sistemas"},
    {"id": "data_engineer", "label": "Ingeniero de Datos"},
    {"id": "data_analyst", "label": "Analista de Datos",
     "aliases": ["analista datos", "analista de data", "data analytics"]},
    {"id": "data_scientist", "label": "Científico de Datos"},
    {"id": "software_developer", "label": "Desarrollador de Software"},
    {"id": "backend_developer", "label": "Desarrollador Backend"},
    {"id": "frontend_developer", "label": "Desarrollador Frontend"},
    {"id": "fullstack_developer", "label": "Desarrollador Full Stack"},
    {"id": "bi_analyst", "label": "Analista BI"},
    {"id": "bi_developer", "label": "Desarrollador BI"},
    {"id": "dba", "label": "Administrador de Bases de Datos"},
    {"id": "qa_engineer", "label": "Ingeniero QA"},
    {"id": "devops_engineer", "label": "Ingeniero DevOps"},
    {"id": "ml_engineer", "label": "Ingeniero de Machine Learning"},
    {"id": "product_manager", "label": "Gerente de Producto"},
    {"id": "project_manager", "label": "Gerente de Proyectos"},
    {"id": "business_analyst", "label": "Analista de Negocios"},
    {"id": "financial_analyst", "label": "Analista Financiero"},
    {"id": "accountant", "label": "Contador"},
    {"id": "commercial_executive", "label": "Ejecutivo Comercial"},
    {"id": "sales_advisor", "label": "Asesor Comercial"},
    {"id": "other", "label": "Otro"},
]

MODALITIES: list[dict] = [
    {"id": "ONSITE", "label": "Presencial"},
    {"id": "HYBRID", "label": "Híbrido"},
    {"id": "REMOTE", "label": "Remoto"},
]

EDUCATION_LEVELS: list[dict] = [
    {"id": "high_school", "label": "Bachillerato"},
    {"id": "technical", "label": "Técnico"},
    {"id": "technologist", "label": "Tecnólogo"},
    {"id": "bachelor", "label": "Pregrado / Universitario"},
    {"id": "specialization", "label": "Especialización"},
    {"id": "master", "label": "Maestría"},
    {"id": "phd", "label": "Doctorado"},
    {"id": "course", "label": "Curso / Diplomado"},
    {"id": "language", "label": "Idioma"},
    {"id": "other", "label": "Otro"},
]

ENTRY_STATUS: list[dict] = [
    {"id": "finished", "label": "Finalizado"},
    {"id": "in_progress", "label": "En curso"},
    {"id": "abandoned", "label": "Abandonado"},
]

LANGUAGES: list[dict] = [
    {"id": "es", "label": "Español"},
    {"id": "en", "label": "Inglés"},
    {"id": "pt", "label": "Portugués"},
    {"id": "fr", "label": "Francés"},
    {"id": "de", "label": "Alemán"},
    {"id": "it", "label": "Italiano"},
]

LANGUAGE_LEVELS: list[dict] = [
    {"id": "A1", "label": "A1"},
    {"id": "A2", "label": "A2"},
    {"id": "B1", "label": "B1"},
    {"id": "B2", "label": "B2"},
    {"id": "C1", "label": "C1"},
    {"id": "C2", "label": "C2"},
    {"id": "native", "label": "Nativo"},
]

CONTRACT_TYPES: list[dict] = [
    {"id": "indefinite", "label": "Indefinido"},
    {"id": "fixed_term", "label": "Término fijo"},
    {"id": "services", "label": "Prestación de servicios"},
    {"id": "freelance", "label": "Freelance"},
    {"id": "internship", "label": "Práctica / Pasantía"},
    {"id": "other", "label": "Otro"},
]

COUNTRIES: list[dict] = [
    {"id": "CO", "label": "Colombia"},
    {"id": "MX", "label": "México"},
    {"id": "AR", "label": "Argentina"},
    {"id": "CL", "label": "Chile"},
    {"id": "PE", "label": "Perú"},
    {"id": "US", "label": "Estados Unidos"},
    {"id": "ES", "label": "España"},
    {"id": "REMOTE", "label": "Remoto"},
    {"id": "ANY", "label": "Cualquier ubicación"},
]

CITIES: list[dict] = [
    {"id": "bogota", "label": "Bogotá", "country": "CO"},
    {"id": "medellin", "label": "Medellín", "country": "CO"},
    {"id": "cali", "label": "Cali", "country": "CO"},
    {"id": "barranquilla", "label": "Barranquilla", "country": "CO"},
    {"id": "cartagena", "label": "Cartagena", "country": "CO"},
    {"id": "bucaramanga", "label": "Bucaramanga", "country": "CO"},
    {"id": "pereira", "label": "Pereira", "country": "CO"},
    {"id": "santa_marta", "label": "Santa Marta", "country": "CO"},
    {"id": "cucuta", "label": "Cúcuta", "country": "CO"},
    {"id": "ibague", "label": "Ibagué", "country": "CO"},
    {"id": "pasto", "label": "Pasto", "country": "CO"},
    {"id": "manizales", "label": "Manizales", "country": "CO"},
    {"id": "neiva", "label": "Neiva", "country": "CO"},
    {"id": "villavicencio", "label": "Villavicencio", "country": "CO"},
    {"id": "armenia", "label": "Armenia", "country": "CO"},
    {"id": "valledupar", "label": "Valledupar", "country": "CO"},
    {"id": "monteria", "label": "Montería", "country": "CO"},
    {"id": "tunja", "label": "Tunja", "country": "CO"},
    {"id": "popayan", "label": "Popayán", "country": "CO"},
    {"id": "sincelejo", "label": "Sincelejo", "country": "CO"},
    {"id": "mexico_city", "label": "Ciudad de México", "country": "MX"},
    {"id": "buenos_aires", "label": "Buenos Aires", "country": "AR"},
    {"id": "santiago_cl", "label": "Santiago", "country": "CL"},
    {"id": "lima", "label": "Lima", "country": "PE"},
    {"id": "remote", "label": "Remoto", "country": "REMOTE"},
    {"id": "anywhere", "label": "Cualquier ubicación", "country": "ANY"},
]


def _match_catalog(raw: str | None, items: list[dict]) -> dict | None:
    """Busca item por id exacto, label normalizado o id con espacios
    ('data_analyst' == 'Data Analyst' == 'data analyst'). Asi distintas
    variantes del mismo concepto colapsan a un solo id."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    for item in items:
        if item["id"] == text:
            return item
    wanted = norm_text(text)
    for item in items:
        if norm_text(item["label"]) == wanted:
            return item
    for item in items:
        if item["id"].replace("_", " ") == wanted:
            return item
    for item in items:
        for alias in item.get("aliases", []):
            if norm_text(alias) == wanted:
                return item
    return None


def norm_title(raw: str | None) -> dict | None:
    """Titulo profesional -> item del catalogo o None (usar 'Otro')."""
    return _match_catalog(raw, PROFESSIONAL_TITLES)


def norm_modality(raw: str | None) -> str | None:
    """Modalidad -> ONSITE | HYBRID | REMOTE | None."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    if text in ("ONSITE", "HYBRID", "REMOTE"):
        return text
    lowered = norm_text(text)
    mapping = {
        "presencial": "ONSITE", "oficina": "ONSITE", "onsite": "ONSITE",
        "hibrido": "HYBRID", "hibrida": "HYBRID", "hybrid": "HYBRID",
        "mixto": "HYBRID", "mixta": "HYBRID",
        "remoto": "REMOTE", "remota": "REMOTE", "remote": "REMOTE",
        "casa": "REMOTE", "virtual": "REMOTE",
    }
    return mapping.get(lowered)


def norm_city(raw: str | None) -> dict | None:
    """Ciudad -> {id, label, country} o None."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    for city in CITIES:
        if city["id"] == text:
            return city
    wanted = norm_text(text)
    # "Bogotá D.C." / "Bogota, Colombia" -> bogota (quita pais y
    # sufijos como d.c./dc antes de comparar).
    first = wanted.split(",")[0].strip()
    first = re.sub(r"\s+d\.?\s*c\.?$", "", first).strip()
    first = re.sub(r"\s+dc$", "", first).strip()
    candidates = {wanted, first}
    for city in CITIES:
        if norm_text(city["label"]) in candidates:
            return city
    return None


def norm_language(raw: str | None) -> dict | None:
    return _match_catalog(raw, LANGUAGES)


def norm_language_level(raw: str | None) -> str | None:
    """Nivel -> A1..C2/Nativo o None (nunca texto libre)."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    valid = {item["id"] for item in LANGUAGE_LEVELS}
    if text in valid:
        return text
    upper = text.upper().replace("NATIVO", "native").replace("NATIVE", "native")
    if upper in valid:
        return upper
    return None


def norm_education_level(raw: str | None) -> str | None:
    item = _match_catalog(raw, EDUCATION_LEVELS)
    return item["id"] if item else None


def get_catalogs() -> dict:
    """Todo lo que la UI necesita para selects/autocompletes."""
    return {
        "professional_titles": PROFESSIONAL_TITLES,
        "modalities": MODALITIES,
        "education_levels": EDUCATION_LEVELS,
        "entry_status": ENTRY_STATUS,
        "languages": LANGUAGES,
        "language_levels": LANGUAGE_LEVELS,
        "contract_types": CONTRACT_TYPES,
        "countries": COUNTRIES,
        "cities": CITIES,
    }
