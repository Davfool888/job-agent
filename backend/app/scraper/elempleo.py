"""Scraper de ElEmpleo (elempleo.com/co).

URLs verificadas (sep-2026):
  listado: https://www.elempleo.com/co/ofertas-empleo/trabajo-{slug}
  detalle: https://www.elempleo.com/co/ofertas-trabajo/{slug}-{id}

Cada tarjeta trae datos estructurados en el atributo
`data-ga4-offerdata` (JSON: title, company, location, salary, tags):

  div.result-item > div[data-ga4-offerdata][data-url]
"""
from __future__ import annotations

import json
import logging
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.config import ELEMPLEO_BASE_URL
from app.config import USER_AGENT
from app.scraper.base import BaseScraper
from app.scraper.base import clean_text
from app.scraper.base import parse_posted_datetime
from app.scraper.base import slugify_query

logger = logging.getLogger(__name__)


def parse_elempleo_cards(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()

    for card in soup.select("div.result-item"):
        holder = card.select_one("[data-ga4-offerdata]")
        if not holder:
            continue
        try:
            meta = json.loads(holder.get("data-ga4-offerdata", "{}"))
        except ValueError:
            continue

        rel = holder.get("data-url") or ""
        link = card.select_one("h2.item-title a[href]")
        if link and link.get("href"):
            rel = link["href"]
        if not rel:
            continue
        url = urljoin(base_url, rel).split("#")[0]
        if "/ofertas-trabajo/" not in url or url in seen:
            continue
        seen.add(url)

        title = clean_text(
            meta.get("title")
            or (link.get_text(" ", strip=True) if link else "")
        )
        if not title:
            continue

        # Snippet descriptivo de la tarjeta (el parrafo mas largo).
        description = ""
        for p in card.select("p"):
            candidate = clean_text(p.get_text(" ", strip=True))
            if len(candidate) > len(description):
                description = candidate
        if len(description) < 80:
            description = ""

        # Fecha relativa de la tarjeta ("Hace 6 días").
        published_text = ""
        for el in card.select("span, small, p"):
            text = clean_text(el.get_text(" ", strip=True))
            if re.search(r"\bhace\b|\bayer\b|\bhoy\b", text, re.I) and len(
                text
            ) < 40:
                published_text = text
                break

        jobs.append(
            {
                "title": title,
                "company": clean_text(meta.get("company")),
                "location": clean_text(meta.get("location")),
                "url": url,
                "description": description,
                "salary": clean_text(meta.get("salary")),
                "published_text": published_text,
                "published_at": parse_posted_datetime(published_text),
                "tags": [
                    t.strip()
                    for t in (meta.get("tags") or "").split(",")
                    if t.strip()
                ],
                "source": "elempleo",
            }
        )

    return jobs


def parse_elempleo_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    # Preferido: schema.org/JobPosting embebido (titulo + descripcion
    # completos, sin renderizado de cliente).
    title = ""
    description = ""
    company = ""
    published_text = ""
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text())
        except ValueError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                continue
            title = clean_text(item.get("title", ""))
            raw_desc = item.get("description", "")
            description = clean_text(
                BeautifulSoup(raw_desc, "html.parser").get_text(" ", strip=True)
            )
            org = item.get("hiringOrganization") or {}
            company = clean_text(
                org.get("name", "") if isinstance(org, dict) else ""
            )
            # Fecha exacta: "datePosted": "2026-9-22".
            published_text = clean_text(item.get("datePosted", ""))
            if description:
                break
        if description:
            break

    if not title:
        title_el = soup.find("h1")
        title = clean_text(
            title_el.get_text(" ", strip=True) if title_el else ""
        )

    if not description:
        for selector in (
            ".job-description",
            "[class*=descripcion]",
            "div[class*=offer-detail]",
            "main",
        ):
            container = soup.select_one(selector)
            if not container:
                continue
            texts = [
                clean_text(p.get_text(" ", strip=True))
                for p in container.select("p, li")
            ]
            texts = [t for t in texts if len(t) > 40]
            if texts:
                description = "\n\n".join(texts[:40])
                break

    if not description:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            description = clean_text(meta["content"])

    return {
        "title": title,
        "company": company,
        "description": description,
        "tags": [],
        "requirements": [],
        "skills": [],
        "published_text": published_text,
        "published_at": parse_posted_datetime(published_text),
    }


class ElEmpleoScraper(BaseScraper):
    source = "elempleo"

    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        super().__init__(ELEMPLEO_BASE_URL, USER_AGENT, delay, max_retries)

    def _build_search_url(self, query: str, page: int = 1) -> str:
        slug = slugify_query(query)
        if not slug:
            raise ValueError("La consulta de busqueda esta vacia.")
        url = f"{self.base_url}/co/ofertas-empleo/trabajo-{slug}"
        if page > 1:
            url = f"{url}?pagina={page}"
        return url

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
            logger.info("Consultando %s", url)
            html = self._get(url)
            jobs = parse_elempleo_cards(html, self.base_url)
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
        html = self._get(url)
        return parse_elempleo_detail(html)
