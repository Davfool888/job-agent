from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.scraper.base import parse_posted_datetime


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split())


def _strip_fragment(url: str) -> str:
    # Computrabajo agrega #lc=ListOffers-... a cada oferta; lo quitamos
    # para deduplicar y guardar URLs canonicas.
    return url.split("#")[0]


def parse_job_cards(html: str, base_url: str) -> list[dict]:
    """Parsea el listado de Computrabajo con su DOM real.

    Estructura verificada (co.computrabajo.com, sep-2026):
      article.box_offer[data-id]
        h2 > a.js-o-link[href="/ofertas-de-trabajo/..."]  -> titulo + url
        a[offer-grid-article-company-url]                 -> empresa
        p.fs16 (2do) > span.mr10                          -> ubicacion
        p.fs13.fc_aux                                     -> fecha publicacion
        div.fs13                                          -> modalidad
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen_urls: set[str] = set()

    cards = soup.select("article.box_offer")
    if not cards:
        # Fallback por si Computrabajo cambia clases.
        cards = soup.select("article[data-id]")

    for card in cards:
        link = card.select_one("a.js-o-link[href]")
        if not link:
            link = card.select_one("h2 a[href], h3 a[href]")

        if not link:
            continue

        href = (link.get("href") or "").strip()
        if not href or href.startswith("javascript"):
            continue

        url = _strip_fragment(urljoin(base_url, href))
        # Solo ofertas reales, ignora links a empresas/salarios.
        if "/ofertas-de-trabajo/" not in url and "/oferta-de-trabajo-" not in url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = clean_text(link.get_text(" ", strip=True))
        if not title:
            continue

        company_el = card.select_one("a[offer-grid-article-company-url]")
        company = clean_text(
            company_el.get_text(" ", strip=True) if company_el else ""
        )
        # Fallback: primer p.fs16 suele ser "rating + empresa".
        if not company:
            first_p = card.select_one("p.fs16")
            if first_p:
                raw = clean_text(first_p.get_text(" ", strip=True))
                # Quita el rating ("4,4 NTT DATA...") -> "NTT DATA..."
                company = re.sub(r"^[\d,.\s\*]+", "", raw).strip()

        location = ""
        paragraphs = card.select("p.fs16")
        if len(paragraphs) >= 2:
            location = clean_text(paragraphs[1].get_text(" ", strip=True))
        elif paragraphs:
            # Si solo hay un p, ese es empresa; ubicacion queda vacia.
            location = ""

        date_el = card.select_one("p.fs13.fc_aux")
        published = clean_text(
            date_el.get_text(" ", strip=True) if date_el else ""
        )

        modality_el = card.select_one("div.fs13")
        modality = clean_text(
            modality_el.get_text(" ", strip=True) if modality_el else ""
        )

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
                "modality": modality,
                "source": "computrabajo",
            }
        )

    return jobs


def parse_total_offers(html: str) -> int | None:
    """Extrae el total ('765 Ofertas de trabajo...') del h1.title_page."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1.title_page") or soup.find("h1")
    if not h1:
        return None
    match = re.search(r"([\d.,]+)", clean_text(h1.get_text(" ", strip=True)))
    if not match:
        return None
    try:
        return int(match.group(1).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def parse_job_detail(html: str) -> dict:
    """Parsea la pagina de detalle de una oferta.

    Estructura verificada:
      h1.box_detail / h1               -> titulo
      div[div-link=oferta] > p.mbB     -> descripcion larga
      div[div-link=oferta] span.tag    -> salario, contrato, jornada
      ul.disc li                       -> requisitos (educacion, experiencia)
    """
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h1.box_detail") or soup.find("h1")
    title = clean_text(
        title_el.get_text(" ", strip=True) if title_el else ""
    )

    container = soup.select_one("div[div-link='oferta'], div[div-link=oferta]")
    description = ""
    tags: list[str] = []
    requirements: list[str] = []

    if container:
        paragraphs = container.select("p.mbB")
        # El primer p.mbB largo es la descripcion; los cortos son extras.
        texts = [
            clean_text(p.get_text(" ", strip=True))
            for p in paragraphs
        ]
        texts = [t for t in texts if t]
        description = "\n\n".join(texts)

        tags = [
            clean_text(s.get_text(" ", strip=True))
            for s in container.select("span.tag")
        ]
        tags = [t for t in tags if t]

        requirements = [
            clean_text(li.get_text(" ", strip=True))
            for li in container.select("ul.disc li")
        ]
        requirements = [r for r in requirements if r]

    # Fallback: meta description si no hay contenedor.
    if not description:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            description = clean_text(meta["content"])

    skills = [
        clean_text(s.get_text(" ", strip=True))
        for s in soup.select("[data-skill-id]")
    ]
    skills = [s for s in skills if s]

    # Fecha exacta de publicacion (JSON-LD: "datePosted": "2026-08-26").
    published_text = ""
    published_at = None
    date_match = re.search(r'"datePosted"\s*:\s*"([^"]+)"', html)
    if date_match:
        published_text = clean_text(date_match.group(1))
        published_at = parse_posted_datetime(published_text)

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "requirements": requirements,
        "skills": skills,
        "published_text": published_text,
        "published_at": published_at,
    }
