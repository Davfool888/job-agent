"""Job Discovery Agent (§4): coordina scrapers + señales + dedup.

Pipeline: queries por capas -> scraper -> normalize -> dedup
(external_id > URL > hash > huella) -> prefilter -> candidatos
al Job Analysis Agent. No analiza con IA; no decide relevancia final.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.analysis.discovery import PACKS
from app.analysis.discovery import discover as run_discovery

logger = logging.getLogger(__name__)


class JobDiscoveryAgent:
    """Orquestador delgado sobre analysis/discovery (motor reutilizado)."""

    def available_packs(self) -> dict[str, list[str]]:
        return {name: list(queries) for name, queries in PACKS.items()}

    def discover(
        self,
        db: Session,
        source: str = "computrabajo",
        packs: list[str] | None = None,
        queries: list[str] | None = None,
        pages: int = 1,
        max_details: int = 15,
        delay: float = 1.0,
    ) -> dict:
        return run_discovery(
            db,
            source=source,
            packs=packs,
            queries=queries,
            pages=pages,
            max_details=max_details,
            delay=delay,
        )
