"""Registro de fuentes de empleo.

Agregar una fuente nueva = crear su Scraper + una linea aqui.
El endpoint /jobs/search usa `get_scraper(source)`.
"""
from __future__ import annotations

from app.scraper.base import BaseScraper
from app.scraper.computrabajo import ComputrabajoScraper
from app.scraper.elempleo import ElEmpleoScraper
from app.scraper.indeed import IndeedScraper
from app.scraper.linkedin import LinkedinScraper
from app.scraper.magneto import MagnetoScraper

SOURCES: dict[str, type[BaseScraper]] = {
    "computrabajo": ComputrabajoScraper,
    "magneto": MagnetoScraper,
    "elempleo": ElEmpleoScraper,
    # indeed: parser verificado, pero Cloudflare/captcha lo bloquea de
    # forma intermitente (403). Se incluye; si falla, /jobs/search
    # responde 502 con el motivo en vez de datos falsos.
    "indeed": IndeedScraper,
    "linkedin": LinkedinScraper,
}


def available_sources() -> list[str]:
    return sorted(SOURCES.keys())


def get_scraper(source: str) -> BaseScraper:
    key = (source or "").strip().lower()
    if key not in SOURCES:
        raise ValueError(
            f"Fuente desconocida: {source}. "
            f"Disponibles: {', '.join(available_sources())}"
        )
    return SOURCES[key]()
