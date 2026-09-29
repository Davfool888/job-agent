from __future__ import annotations

import logging
import time

from app.config import COMPUTRABAJO_BASE_URL
from app.config import USER_AGENT
from app.scraper.base import BaseScraper
from app.scraper.base import slugify_query
from app.scraper.parser import parse_job_cards
from app.scraper.parser import parse_job_detail
from app.scraper.parser import parse_total_offers

logger = logging.getLogger(__name__)

# Re-export para compatibilidad con codigo que lo importaba de aqui.
__all__ = ["ComputrabajoScraper", "slugify_query"]


class ComputrabajoScraper(BaseScraper):
    source = "computrabajo"

    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        super().__init__(COMPUTRABAJO_BASE_URL, USER_AGENT, delay, max_retries)

    def _build_search_url(self, query: str, page: int = 1) -> str:
        slug = slugify_query(query)
        if not slug:
            raise ValueError("La consulta de busqueda esta vacia.")
        url = f"{self.base_url}/trabajo-de-{slug}"
        if page > 1:
            url = f"{url}?p={page}"
        return url

    def search(
        self,
        query: str,
        max_pages: int = 1,
        include_details: bool = False,
    ) -> list[dict]:
        """Busca ofertas. Pagina con ?p=2, ?p=3... hasta max_pages."""
        max_pages = max(1, min(max_pages, 10))
        all_jobs: list[dict] = []
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            url = self._build_search_url(query, page)
            logger.info("Consultando %s", url)
            html = self._get(url)
            jobs = parse_job_cards(html, self.base_url)

            if page == 1:
                total = parse_total_offers(html)
                if total is not None:
                    logger.info("Total ofertas reportado: %s", total)

            if not jobs:
                break

            fresh = [j for j in jobs if j["url"] not in seen]
            for job in fresh:
                seen.add(job["url"])
            all_jobs.extend(fresh)

            # Si una pagina trae menos de ~15 resultados, no hay mas paginas.
            if len(jobs) < 5:
                break
            if page < max_pages:
                time.sleep(self.delay)

        if include_details:
            for job in all_jobs:
                try:
                    detail = self.get_job_detail(job["url"])
                    job["description"] = detail.get("description", "")
                    job["tags"] = detail.get("tags", [])
                    job["requirements"] = detail.get("requirements", [])
                    time.sleep(self.delay)
                except Exception as error:  # noqa: BLE001
                    logger.warning(
                        "No se pudo obtener detalle de %s: %s",
                        job["url"],
                        error,
                    )

        return all_jobs

    def get_job_detail(self, url: str) -> dict:
        html = self._get(url)
        return parse_job_detail(html)
