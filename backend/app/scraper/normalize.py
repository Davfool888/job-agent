"""Normalizacion de ofertas (§14): todos los scrapers entregan dicts
con estas claves. El scraper NO analiza; solo descubre y extrae.
"""
from __future__ import annotations

import hashlib

from app.scraper.base import norm_key, repair_encoding

NORMALIZED_KEYS = (
    "source", "external_id", "title", "company", "description",
    "requirements", "responsibilities", "location", "modality",
    "salary", "url", "published_text", "published_at", "sector",
)

# Empresas que ocultan su nombre: colapsar a un solo canónico para que
# el top de stats y la huella de dedup no se partan en 3 variantes.
CONFIDENTIAL_COMPANY_ALIASES = frozenset({
    "importanteempresadelsector",
    "empresaimportante",
    "importanteempresa",
    "empresaconfidencial",
    "confidencial",
    "empresaenconfidencial",
    "confidential",
})

CONFIDENTIAL_COMPANY_CANONICAL = "Confidencial"


def normalize_company(name: str | None) -> str:
    """Colapsa alias de empresa confidencial + repara encoding."""
    text = repair_encoding((name or "").strip())
    text = " ".join(text.split())
    if norm_key(text) in CONFIDENTIAL_COMPANY_ALIASES:
        return CONFIDENTIAL_COMPANY_CANONICAL
    return text


def content_hash_of(description: str | None) -> str | None:
    """Hash del contenido para dedup nivel 3 (requiere texto largo)."""
    text = (description or "").strip()
    if len(text) < 200:
        return None
    return hashlib.sha1(norm_key(text).encode("utf-8")).hexdigest()


def normalize_job(raw: dict) -> dict:
    """Completa claves faltantes con defaults. Acepta dicts viejos
    (computrabajo & co.) sin romperlos."""
    data = dict(raw or {})

    def as_list(value) -> list[str]:
        if isinstance(value, list):
            return [repair_encoding(str(v).strip()) for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [repair_encoding(value.strip())]
        return []

    salary_raw = data.get("salary") or data.get("salary_text") or ""
    if isinstance(salary_raw, list):
        salary_raw = "; ".join(str(s) for s in salary_raw)
    normalized = {
        "source": str(data.get("source") or "computrabajo").strip().lower(),
        "external_id": (str(data.get("external_id") or "").strip() or None),
        "title": repair_encoding((data.get("title") or "").strip()),
        "company": normalize_company(data.get("company")),
        "description": repair_encoding(data.get("description") or ""),
        "requirements": as_list(data.get("requirements")),
        "responsibilities": as_list(data.get("responsibilities")),
        "location": repair_encoding((data.get("location") or "").strip()),
        "modality": repair_encoding((data.get("modality") or "").strip()),
        "salary": repair_encoding(str(salary_raw or "").strip()),
        "url": (data.get("url") or "").strip(),
        "published_text": repair_encoding(
            data.get("published_text") or data.get("published") or ""
        ),
        "published_at": data.get("published_at"),
        "sector": repair_encoding((data.get("sector") or "").strip()),
    }
    # Campos extra que algunos scrapers aportan (se conservan).
    for key in ("tags", "skills", "contract", "jobkey", "job_id",
                "search_profile_ids"):
        if data.get(key) is not None:
            normalized[key] = data[key]
    return normalized
