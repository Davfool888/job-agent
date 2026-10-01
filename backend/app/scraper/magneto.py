"""Scraper de Magneto (magneto365.com/co).

URLs verificadas (sep-2026):
  listado: https://www.magneto365.com/co/trabajos/ofertas-empleo-de-{slug}
           ej: ofertas-empleo-de-desarrollador-software
  detalle: https://www.magneto365.com/co/empleos/{slug}-{id}

Tarjeta (server-rendered):
  article[class*=mg_job_card]
    h2 > a[href*=/co/empleos/]  -> titulo + url
    h3                          -> "Empresa | Contrato"
    p (con $)                   -> salario
    p (sin $)                   -> ubicacion
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.config import MAGNETO_BASE_URL
from app.config import USER_AGENT
from app.scraper.base import BaseScraper
from app.scraper.base import clean_text
from app.scraper.base import filter_by_location
from app.scraper.base import parse_posted_datetime
from app.scraper.base import slugify_query

logger = logging.getLogger(__name__)


def _strip_fragment(url: str) -> str:
    return url.split("#")[0].split("?")[0]


def parse_magneto_cards(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()

    cards = soup.select("article[class*=mg_job_card]")
    if not cards:
        cards = soup.select("article")

    for card in cards:
        link = card.select_one("h2 a[href], a[href*=\\/co\\/empleos\\/]")
        if not link:
            continue
        href = (link.get("href") or "").strip()
        if not href:
            continue
        url = _strip_fragment(urljoin(base_url, href))
        if "/empleos/" not in url or url in seen:
            continue
        seen.add(url)

        title = clean_text(link.get("title") or link.get_text(" ", strip=True))
        if not title:
            continue

        company = ""
        contract = ""
        h3 = card.select_one("h3")
        if h3:
            parts = [p.strip() for p in clean_text(h3.get_text(" ", strip=True)).split("|")]
            company = parts[0] if parts else ""
            contract = parts[1] if len(parts) > 1 else ""

        salary = ""
        location = ""
        for p in card.select("p"):
            text = clean_text(p.get_text(" ", strip=True))
            if not text:
                continue
            if "$" in text and not salary:
                salary = text.rstrip(",")
            elif not location:
                location = text

        jobs.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "description": "",
                "salary": salary,
                "contract": contract,
                "published_text": "",
                "published_at": None,
                "source": "magneto",
            }
        )

    return jobs


def parse_magneto_detail(html: str, url: str = "") -> dict:
    """El detalle es client-rendered, pero la descripcion viaja en los
    flight-data del SSR: "description":"<texto largo>". El titulo se
    toma de og:title o del slug de la URL."""
    import json as _json
    import re as _re

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = clean_text(og["content"].split("|")[0])
    if not title:
        names = _re.findall(r'"name":"([^"]{10,120})"', html)
        for name in names:
            if _re.search(r"\d{4,}", name):
                title = clean_text(name)
                break
    if not title and url:
        slug = url.rstrip("/").split("/")[-1]
        slug = _re.sub(r"-\d+$", "", slug).replace("-", " ")
        title = clean_text(slug).title()

    description = ""
    junk_markers = (
        "términos y condiciones", "terminos y condiciones",
        "Escribe tu", "contraseña", "contrasena",
    )
    candidates = _re.findall(r'"description":"((?:[^"\\]|\\.){200,6000})"', html)
    best = ""
    for raw in candidates:
        try:
            text = _json.loads(f'"{raw}"')
        except ValueError:
            continue
        text = clean_text(text)
        if any(mark in text for mark in junk_markers):
            continue
        if len(text) > len(best):
            best = text
    description = best.replace("\\n", "\n")

    if not description:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            description = clean_text(meta["content"])

    company = ""
    names = _re.findall(r'"name":"([^"]{3,120})"', html)
    if names:
        company = clean_text(names[0])

    # Fecha exacta en flight-data: "publishDate":"2026-09-29T..." o
    # "datePosted":"2026-08-12".
    published_text = ""
    published_at = None
    date_match = _re.search(
        r'"(?:publishDate|datePosted)\\?":\\?"([^"\\]+)"', html
    )
    if date_match:
        published_text = clean_text(date_match.group(1))
        published_at = parse_posted_datetime(published_text)

    return {
        "title": title,
        "company": company,
        "description": description,
        "tags": [],
        "requirements": [],
        "skills": [],
        "published_text": published_text,
        "published_at": published_at,
    }


class MagnetoScraper(BaseScraper):
    source = "magneto"

    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        super().__init__(MAGNETO_BASE_URL, USER_AGENT, delay, max_retries)

    def _build_search_url(self, query: str, page: int = 1) -> str:
        slug = slugify_query(query)
        if not slug:
            raise ValueError("La consulta de busqueda esta vacia.")
        # NOTA: Magneto solo resuelve slugs de su taxonomia
        # (ej: desarrollador-software). Un slug libre da 500.
        url = f"{self.base_url}/co/trabajos/ofertas-empleo-de-{slug}"
        if page > 1:
            url = f"{url}?page={page}"
        return url

    def _candidate_slugs(self, query: str) -> list[str]:
        """Slug completo + tokens individuales (ej: 'desarrollador python'
        -> ['desarrollador-python', 'desarrollador', 'python'])."""
        full = slugify_query(query)
        tokens = [t for t in full.split("-") if len(t) > 2]
        candidates = [full] + [t for t in tokens if t != full]
        seen: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.append(c)
        return seen

    def _resolve_listing(self, query: str) -> tuple[str, str]:
        """Devuelve (html, slug_usado) del primer slug que resuelva (200).
        Lanza RuntimeError si ninguno resuelve."""
        last_error: Exception | None = None
        for slug in self._candidate_slugs(query):
            url = f"{self.base_url}/co/trabajos/ofertas-empleo-de-{slug}"
            try:
                response = self.session.get(url, timeout=25)
                if response.status_code == 200 and "mg_job_card" in response.text:
                    logger.info("Magneto resolvio categoria '%s'", slug)
                    return response.text, slug
                last_error = RuntimeError(f"HTTP {response.status_code}: {url}")
            except requests.RequestException as error:
                last_error = error
            time.sleep(self.delay)
        raise RuntimeError(
            f"Magneto no tiene categoria para '{query}': {last_error}"
        )

    @staticmethod
    def _relevant(jobs: list[dict], query: str) -> list[dict]:
        """La categoria es mas amplia que la busqueda: ordena primero los
        titulos que contienen TODOS los tokens (ej: python), luego los
        parciales. Si nada coincide, devuelve todo sin ocultar."""
        tokens = [t for t in slugify_query(query).split("-") if len(t) > 2]
        if not tokens:
            return jobs

        def score(job: dict) -> int:
            title_slug = slugify_query(job.get("title", ""))
            return sum(1 for tok in tokens if tok in title_slug)

        ranked = sorted(jobs, key=score, reverse=True)
        return ranked if ranked and score(ranked[0]) > 0 else jobs

    def search(
        self,
        query: str,
        max_pages: int = 1,
        include_details: bool = False,
        location: str | None = None,
    ) -> list[dict]:
        max_pages = max(1, min(max_pages, 10))
        all_jobs: list[dict] = []
        seen: set[str] = set()

        # Pagina 1 resuelve la categoria (con fallback de slugs);
        # paginas 2+ reutilizan el slug resuelto.
        html, slug = self._resolve_listing(query)
        pages_html = {1: html}

        for page in range(1, max_pages + 1):
            if page in pages_html:
                html = pages_html[page]
            else:
                url = (
                    f"{self.base_url}/co/trabajos/"
                    f"ofertas-empleo-de-{slug}?page={page}"
                )
                logger.info("Consultando %s", url)
                html = self._get(url)
            jobs = parse_magneto_cards(html, self.base_url)
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

        all_jobs = self._relevant(all_jobs, query)

        if include_details:
            for job in all_jobs:
                try:
                    detail = self.get_job_detail(job["url"])
                    job["description"] = detail.get("description", "")
                    time.sleep(self.delay)
                except Exception as error:  # noqa: BLE001
                    logger.warning(
                        "No se pudo obtener detalle de %s: %s",
                        job["url"],
                        error,
                    )

        # Magneto lista a nivel nacional: filtra por ciudad aqui.
        return filter_by_location(all_jobs, location)

    def get_job_detail(self, url: str) -> dict:
        html = self._get(url)
        return parse_magneto_detail(html, url)
