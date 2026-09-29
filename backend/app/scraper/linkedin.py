"""Scraper de LinkedIn via API publica de invitado (sin login).

Verificado (sep-2026):
  listado: https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
           ?keywords={q}&location={loc}&start={0,10,...}
  detalle: https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}

Tarjeta:
  div.job-search-card[data-entity-urn=urn:li:jobPosting:{id}]
    h3.base-search-card__title  -> titulo
    h4.base-search-card__subtitle -> empresa
    span.job-search-card__location -> ubicacion
    time[datetime] -> fecha
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse

from bs4 import BeautifulSoup

from app.config import LINKEDIN_BASE_URL
from app.config import USER_AGENT
from app.scraper.base import BaseScraper
from app.scraper.base import clean_text
from app.scraper.base import parse_posted_datetime

logger = logging.getLogger(__name__)

URN_RE = re.compile(r"urn:li:jobPosting:(\d+)")


def parse_linkedin_cards(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()

    for card in soup.select("div.job-search-card[data-entity-urn]"):
        match = URN_RE.search(card.get("data-entity-urn", ""))
        if not match:
            continue
        job_id = match.group(1)
        if job_id in seen:
            continue
        seen.add(job_id)

        title_el = card.select_one("h3.base-search-card__title")
        title = clean_text(
            title_el.get_text(" ", strip=True) if title_el else ""
        )
        if not title:
            continue

        # URL canonica sin tracking: /jobs/view/{slug}-{id}; si no hay
        # slug usable, /jobs/view/x-{id} tambien resuelve.
        url = f"{base_url}/jobs/view/x-{job_id}"
        link = card.select_one("a.base-card__full-link[href]")
        if link and link.get("href"):
            href = link["href"].split("?")[0].replace(
                "co.linkedin.com", "www.linkedin.com"
            )
            if f"-{job_id}" in href:
                url = href

        company_el = card.select_one("h4.base-search-card__subtitle")
        company = clean_text(
            company_el.get_text(" ", strip=True) if company_el else ""
        )

        location_el = card.select_one("span.job-search-card__location")
        location = clean_text(
            location_el.get_text(" ", strip=True) if location_el else ""
        )

        date_el = card.select_one("time[datetime]")
        published = date_el.get("datetime", "") if date_el else ""

        jobs.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description": "",
                "published": published,
                "published_text": published,
                "published_at": parse_posted_datetime(published),
                "job_id": job_id,
                "source": "linkedin",
            }
        )

    return jobs


def parse_linkedin_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h2.top-card-layout__title")
    title = clean_text(title_el.get_text(" ", strip=True) if title_el else "")

    company_el = soup.select_one(
        "a.topcard__org-name-link, span.topcard__flavor"
    )
    company = clean_text(
        company_el.get_text(" ", strip=True) if company_el else ""
    )

    description = ""
    desc_el = soup.select_one("div.description__text")
    if desc_el:
        description = clean_text(desc_el.get_text("\n", strip=True))

    return {
        "title": title,
        "company": company,
        "description": description,
        "tags": [],
        "requirements": [],
        "skills": [],
    }


class LinkedinScraper(BaseScraper):
    source = "linkedin"

    def __init__(self, delay: float = 1.5, max_retries: int = 3):
        super().__init__(LINKEDIN_BASE_URL, USER_AGENT, delay, max_retries)

    def _build_search_url(self, query: str, page: int = 1) -> str:
        if not query.strip():
            raise ValueError("La consulta de busqueda esta vacia.")
        params = urllib.parse.urlencode(
            {
                "keywords": query.strip(),
                "location": "Colombia",
                "start": (page - 1) * 10,
            }
        )
        return (
            f"{self.base_url}/jobs-guest/jobs/api/"
            f"seeMoreJobPostings/search?{params}"
        )

    def search(
        self,
        query: str,
        max_pages: int = 1,
        include_details: bool = False,
    ) -> list[dict]:
        max_pages = max(1, min(max_pages, 10))
        all_jobs: list[dict] = []
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            url = self._build_search_url(query, page)
            logger.info("Consultando %s", url.split("?")[0])
            html = self._get(url)
            jobs = parse_linkedin_cards(html, self.base_url)
            if not jobs:
                break
            fresh = [j for j in jobs if j["url"] not in seen]
            for job in fresh:
                seen.add(job["url"])
            all_jobs.extend(fresh)
            if len(jobs) < 5:
                break
            if page < max_pages:
                time.sleep(self.delay)

        if include_details:
            for job in all_jobs:
                try:
                    detail = self.get_job_detail(job["url"])
                    if detail.get("description"):
                        job["description"] = detail["description"]
                    time.sleep(self.delay)
                except Exception as error:  # noqa: BLE001
                    logger.warning(
                        "No se pudo obtener detalle de %s: %s",
                        job["url"],
                        error,
                    )

        return all_jobs

    def get_job_detail(self, url: str) -> dict:
        match = re.search(r"(\d{6,})", url)
        if match:
            api_url = (
                f"{self.base_url}/jobs-guest/jobs/api/"
                f"jobPosting/{match.group(1)}"
            )
            try:
                return parse_linkedin_detail(self._get(api_url))
            except Exception as error:  # noqa: BLE001
                logger.warning(
                    "Fallo API de detalle LinkedIn, intento pagina: %s", error
                )
        return parse_linkedin_detail(self._get(url))
