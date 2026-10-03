"""Scraper de Indeed Colombia (co.indeed.com).

Verificado (sep-2026):
  listado: https://co.indeed.com/jobs?q={query}&l=Colombia&start={0,10,...}
  detalle: https://co.indeed.com/viewjob?jk={jobkey}

Requiere: visita previa al home (cookies) + headers de navegador
completos; sin eso devuelve 403. Tarjetas:
  div.job_seen_beacon (deduplicar por a.jcs-JobTitle[data-jk])
    a.jcs-JobTitle span[title] -> titulo
    [data-testid=company-name] -> empresa
    [data-testid=text-location] -> ubicacion
    div con $...por mes|COP -> salario
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
from collections.abc import Callable

from bs4 import BeautifulSoup

from app.config import INDEED_BASE_URL
from app.config import USER_AGENT
from app.scraper.base import BaseScraper
from app.scraper.base import clean_text
from app.scraper.base import filter_by_location
from app.scraper.base import parse_posted_datetime

logger = logging.getLogger(__name__)

SALARY_RE = re.compile(r"\$\s?[\d.,]+\s*(?:por\s(?:mes|año|hora)|al\smes|COP|/mes)?", re.I)


def parse_indeed_cards(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()

    for card in soup.select("div.job_seen_beacon"):
        link = card.select_one("a.jcs-JobTitle[data-jk]")
        if not link:
            continue
        jk = (link.get("data-jk") or "").strip()
        if not jk or jk in seen:
            continue
        seen.add(jk)

        title_el = link.select_one("span[title]") or link
        title = clean_text(
            title_el.get("title") or title_el.get_text(" ", strip=True)
        )
        if not title:
            continue

        url = f"{base_url}/viewjob?jk={jk}"

        company_el = card.select_one("[data-testid=company-name]")
        company = clean_text(
            company_el.get_text(" ", strip=True) if company_el else ""
        )
        # Limpia coletillas ("BPM Consulting\n3,9" -> nombre).
        company = re.split(r"\n|\d,\d", company)[0].strip()

        location_el = card.select_one("[data-testid=text-location]")
        location = clean_text(
            location_el.get_text(" ", strip=True) if location_el else ""
        )

        salary = ""
        for div in card.select("div"):
            text = clean_text(div.get_text(" ", strip=True))
            if len(text) > 70:
                continue
            match = SALARY_RE.search(text)
            if match and re.search(r"\d", text):
                salary = text
                break

        jobs.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description": "",
                "salary": salary,
                "published_text": "",
                "published_at": None,
                "jobkey": jk,
                "source": "indeed",
            }
        )

    return jobs


def parse_indeed_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    h1 = soup.select_one("h1.jobsearch-JobInfoHeader-title, h1")
    if h1:
        title = clean_text(h1.get_text(" ", strip=True))

    description = ""
    desc_el = soup.select_one("#jobDescriptionText")
    if desc_el:
        description = clean_text(desc_el.get_text("\n", strip=True))

    company = ""
    comp_el = soup.select_one('[data-testid="jobsearch-CompanyInfo"]')
    if comp_el:
        company = clean_text(comp_el.get_text(" ", strip=True)[:120])

    if not description:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            description = clean_text(meta["content"])

    # Fecha relativa si aparece ("hace 3 días", "Publicado hace...").
    published_text = ""
    for el in soup.select("span, div"):
        text = clean_text(el.get_text(" ", strip=True))
        if len(text) > 60:
            continue
        if re.search(r"\bhace\s+\d+\s+\w+|publicad[oa]\s+hace", text, re.I):
            published_text = text
            break

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


class IndeedScraper(BaseScraper):
    source = "indeed"

    def __init__(self, delay: float = 2.0, max_retries: int = 3):
        super().__init__(INDEED_BASE_URL, USER_AGENT, delay, max_retries)
        self.session.headers.update(
            {
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,*/*;q=0.8"
                ),
                "Sec-Ch-Ua": '"Chromium";v="126", "Google Chrome";v="126"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-User": "?1",
                "Sec-Fetch-Dest": "document",
            }
        )
        self._warmed_up = False

    def _warmup(self) -> None:
        """El home deja cookies sin las cuales /jobs da 403."""
        if self._warmed_up:
            return
        try:
            self.session.get(f"{self.base_url}/", timeout=20)
            self._warmed_up = True
        except Exception as error:  # noqa: BLE001
            logger.warning("Warmup de Indeed fallo: %s", error)

    def _build_search_url(
        self, query: str, page: int = 1, location: str | None = None
    ) -> str:
        if not query.strip():
            raise ValueError("La consulta de busqueda esta vacia.")
        place = (location or "Colombia").strip() or "Colombia"
        params = urllib.parse.urlencode(
            {"q": query.strip(), "l": place, "start": (page - 1) * 10}
        )
        return f"{self.base_url}/jobs?{params}"

    def search(
        self,
        query: str,
        max_pages: int = 1,
        include_details: bool = False,
        location: str | None = None,
        on_page: Callable[[list[dict], int], None] | None = None,
    ) -> list[dict]:
        max_pages = max(1, min(max_pages, 5))
        self._warmup()
        all_jobs: list[dict] = []
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            url = self._build_search_url(query, page, location)
            logger.info("Consultando %s", url)
            headers = {"Referer": f"{self.base_url}/"}
            html = self._get_with_headers(url, headers)
            jobs = parse_indeed_cards(html, self.base_url)
            if not jobs:
                break
            fresh = [j for j in jobs if j["url"] not in seen]
            for job in fresh:
                seen.add(job["url"])
            all_jobs.extend(fresh)
            if on_page is not None:
                on_page(list(fresh), page)
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

        return filter_by_location(all_jobs, location)

    def _get_with_headers(self, url: str, extra: dict) -> str:
        blocks: list[str] = []
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, headers=extra, timeout=25)
                if response.status_code in (403, 429):
                    blocks.append(f"HTTP {response.status_code}")
                    self._warmed_up = False
                    self._warmup()
                    time.sleep(self.delay * attempt * 2)
                    continue
                response.raise_for_status()
                return response.text
            except Exception as error:  # noqa: BLE001
                blocks.append(f"{type(error).__name__}: {error}")
                logger.warning(
                    "Error consultando %s (intento %s/%s): %s",
                    url,
                    attempt,
                    self.max_retries,
                    error,
                )
                time.sleep(self.delay * attempt)
        raise RuntimeError(
            "Indeed bloqueo la consulta (Cloudflare/captcha). "
            f"Bloqueos: {'; '.join(blocks) or 'desconocido'}. "
            "Reintenta mas tarde o con mayor intervalo."
        )

    def get_job_detail(self, url: str) -> dict:
        self._warmup()
        html = self._get_with_headers(url, {"Referer": f"{self.base_url}/jobs"})
        return parse_indeed_detail(html)
