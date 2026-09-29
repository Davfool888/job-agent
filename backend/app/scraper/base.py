"""Infraestructura compartida por todos los scrapers de fuentes.

Cada fuente (computrabajo, magneto, elempleo, ...) implementa
`BaseScraper` y devuelve dicts con esta forma:

    {
        "title": str, "company": str, "location": str,
        "url": str (canonica, sin fragmentos),
        "description": str, "source": "<nombre-fuente>",
        "published_text": str (ej: "Hace 3 horas", puede ser ""),
        "published_at": datetime | None (fecha real de publicacion),
        ... campos extra libres (salary, modality, ...)
    }
"""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
import hashlib
import logging
import re
import time
import unicodedata

import requests

logger = logging.getLogger(__name__)


def slugify_query(query: str) -> str:
    """'Desarrollador Python Senior' -> 'desarrollador-python-senior'."""
    value = unicodedata.normalize("NFKD", query.strip().lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-z0-9\s-]", "", value)
    value = re.sub(r"[\s_]+", "-", value.strip())
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(text.split())


def norm_key(text: str | None) -> str:
    """Normaliza para comparar/huellas: minusculas, sin tildes,
    solo alfanumericos."""
    value = unicodedata.normalize("NFKD", (text or "").strip().lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", value)


def norm_location(text: str | None) -> str:
    """Solo la primera parte ('Bogotá, D.C.' -> 'bogota') para que
    variantes del mismo lugar compartan huella."""
    return norm_key((text or "").split(",")[0])


def fingerprint_of(title: str | None, company: str | None,
                   location: str | None = None) -> str:
    """Huella de 'la misma oferta': titulo+empresa+ubicacion
    normalizados. Dos republicaciones (distinta URL, mismo contenido)
    comparten huella aunque el scraper las vea como filas distintas."""
    raw = "|".join([norm_key(title), norm_key(company),
                    norm_location(location)])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


_RELATIVE_RE = re.compile(
    r"hace\s+(\d+)\s*(minuto|hora|d[ií]a|semana|mes)",
    re.IGNORECASE,
)
_JUST_NOW_RE = re.compile(
    r"^(hoy|ayer|reci[eé]n|ahora|justo ahora|nueva?)$", re.IGNORECASE
)


def _parse_ymd(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def parse_posted_datetime(raw: str | None,
                          now: datetime | None = None) -> datetime | None:
    """Convierte fecha de publicacion a datetime (UTC ingenuo).

    Acepta ISO ('2026-9-22', '2026-09-29T03:23:28.097Z', '2026-09-18'),
    relativos en español ('Hace 5 minutos', 'Hace 3 horas',
    'Hace 2 días', 'Hace 1 semana', 'Hace 3 meses', 'Ayer', 'Hoy')
    y Unix timestamp. Devuelve None si no se puede interpretar.
    """
    if not raw:
        return None
    now = now or datetime.utcnow()
    text = clean_text(raw)

    # ISO: primero datetime completo (conserva hora), luego solo fecha.
    iso_full = re.search(r"\d{4}-\d{1,2}-\d{1,2}T\d{1,2}:\d{2}(:\d{2})?", text)
    if iso_full:
        try:
            return datetime.fromisoformat(
                iso_full.group(0).replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            pass
    iso = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso:
        # Manual (fromisoformat exige cero-padding en 3.11).
        return _parse_ymd(int(iso.group(1)), int(iso.group(2)),
                          int(iso.group(3)))
    slash = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if slash:
        try:
            day, month, year = map(int, slash.groups())
            return datetime(year, month, day)
        except ValueError:
            pass
    if re.fullmatch(r"\d{10}(\.\d+)?", text):
        try:
            return datetime.utcfromtimestamp(float(text))
        except (ValueError, OSError, OverflowError):
            pass

    low = text.lower()
    if low.startswith("ayer"):
        return now - timedelta(days=1)
    if _JUST_NOW_RE.match(low):
        return now

    match = _RELATIVE_RE.search(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("minuto"):
            return now - timedelta(minutes=amount)
        if unit.startswith("hora"):
            return now - timedelta(hours=amount)
        if unit.startswith("d"):
            return now - timedelta(days=amount)
        if unit.startswith("semana"):
            return now - timedelta(weeks=amount)
        if unit.startswith("mes"):
            return now - timedelta(days=30 * amount)

    return None


class BaseScraper:
    source: str = "unknown"

    def __init__(
        self,
        base_url: str,
        user_agent: str,
        delay: float = 1.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
            }
        )

    def _get(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=25)
                if response.status_code in (403, 429):
                    wait = self.delay * attempt * 2
                    logger.warning(
                        "%s devolvio %s, reintento %s/%s en %ss: %s",
                        self.source,
                        response.status_code,
                        attempt,
                        self.max_retries,
                        wait,
                        url,
                    )
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                return response.text
            except requests.RequestException as error:
                last_error = error
                logger.warning(
                    "Error consultando %s (intento %s/%s): %s",
                    url,
                    attempt,
                    self.max_retries,
                    error,
                )
                time.sleep(self.delay * attempt)
        raise RuntimeError(
            f"No se pudo consultar {self.source} tras "
            f"{self.max_retries} intentos: {last_error}"
        )

    def search(
        self,
        query: str,
        max_pages: int = 1,
        include_details: bool = False,
    ) -> list[dict]:
        raise NotImplementedError

    def get_job_detail(self, url: str) -> dict:
        raise NotImplementedError
