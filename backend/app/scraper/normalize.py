"""Normalizacion de ofertas (§14): todos los scrapers entregan dicts
con estas claves. El scraper NO analiza; solo descubre y extrae.
"""
from __future__ import annotations

import hashlib

from app.scraper.base import norm_key

NORMALIZED_KEYS = (
    "source", "external_id", "title", "company", "description",
    "requirements", "responsibilities", "location", "modality",
    "salary", "url", "published_text", "published_at", "sector",
)


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
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    salary_raw = data.get("salary") or data.get("salary_text") or ""
    if isinstance(salary_raw, list):
        salary_raw = "; ".join(str(s) for s in salary_raw)
    normalized = {
        "source": str(data.get("source") or "computrabajo").strip().lower(),
        "external_id": (str(data.get("external_id") or "").strip() or None),
        "title": (data.get("title") or "").strip(),
        "company": (data.get("company") or "").strip(),
        "description": data.get("description") or "",
        "requirements": as_list(data.get("requirements")),
        "responsibilities": as_list(data.get("responsibilities")),
        "location": (data.get("location") or "").strip(),
        "modality": (data.get("modality") or "").strip(),
        "salary": str(salary_raw or "").strip(),
        "url": (data.get("url") or "").strip(),
        "published_text": (
            data.get("published_text") or data.get("published") or ""
        ),
        "published_at": data.get("published_at"),
        "sector": (data.get("sector") or "").strip(),
    }
    # Campos extra que algunos scrapers aportan (se conservan).
    for key in ("tags", "skills", "contract", "jobkey", "job_id",
                "search_profile_ids"):
        if data.get(key) is not None:
            normalized[key] = data[key]
    return normalized
