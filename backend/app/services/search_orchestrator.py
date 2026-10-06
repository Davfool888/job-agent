"""Orquestador de busqueda (Fase 3).

Unifica el pipeline que estaba triplicado en:
- `GET /jobs/search` (routers/discovery.py)
- `GET /jobs/search/stream` worker (routers/discovery.py)
- `scheduler.run_profile` (scheduler.py)

Misma semantica en los tres (sin cambiar ranking ni dedup):
scrape -> filtro edad (/ubicacion donde ya existia) -> save_jobs
-> enrich_and_analyze. Los routers/scheduler conservan sus
try/except y formatos de error/respuesta; aqui solo vive la
mecanica compartida mas un circuit-breaker por fuente.

Circuit-breaker: si una fuente falla N veces seguidas en la
ventana, se enfria OPEN_SECONDS y `scrape_with` lanza
CircuitOpen en vez de golpear la red. Umbrales conservadores
para no alterar el comportamiento normal; solo protege contra
fuentes caidas que el scheduler reintentaria cada tick.
"""
from __future__ import annotations

import threading
import time

FAILURE_THRESHOLD = 5
WINDOW_SECONDS = 300.0
OPEN_SECONDS = 60.0


class CircuitOpen(Exception):
    """La fuente esta en enfriamiento tras fallos consecutivos."""


_lock = threading.Lock()
_failures: dict[str, list[float]] = {}
_opened_until: dict[str, float] = {}


def reset_circuit(source: str | None = None) -> None:
    """Limpia el breaker (tests). Sin args limpia todo."""
    with _lock:
        if source is None:
            _failures.clear()
            _opened_until.clear()
        else:
            _failures.pop(str(source), None)
            _opened_until.pop(str(source), None)


def _now() -> float:
    return time.monotonic()


def circuit_check(source: str) -> None:
    """Lanza CircuitOpen si la fuente esta enfriandose."""
    key = str(source)
    with _lock:
        until = _opened_until.get(key, 0.0)
        if _now() < until:
            raise CircuitOpen(
                f"fuente {key} en enfriamiento "
                f"({int(until - _now())}s restantes)"
            )


def circuit_success(source: str) -> None:
    with _lock:
        _failures.pop(str(source), None)
        _opened_until.pop(str(source), None)


def circuit_failure(source: str) -> None:
    key = str(source)
    now = _now()
    with _lock:
        recent = [t for t in _failures.get(key, [])
                  if now - t < WINDOW_SECONDS]
        recent.append(now)
        _failures[key] = recent
        if len(recent) >= FAILURE_THRESHOLD:
            _opened_until[key] = now + OPEN_SECONDS


def resolve_scraper(source: str):
    """Igual que registry.get_scraper (ValueError si fuente mala).

    Import lazy via modulo para que los tests puedan parchar
    `app.scraper.registry.get_scraper` como hasta ahora.
    """
    from app.scraper import registry

    return registry.get_scraper(source)


def scrape_with(scraper, source_key: str, q: str, max_pages: int = 1,
                include_details: bool = False, location=None,
                on_page=None) -> list:
    """scraper.search con breaker. ValueError (input) no cuenta como
    fallo; Exception (red/sitio) si. Propaga sin traducir: cada
    llamador conserva su mapeo a 400/502 o su registro de errores."""
    circuit_check(source_key)
    kwargs: dict = {"max_pages": max_pages,
                    "include_details": include_details}
    if location is not None:
        kwargs["location"] = location
    if on_page is not None:
        kwargs["on_page"] = on_page
    try:
        found = scraper.search(q, **kwargs)
    except ValueError:
        raise
    except Exception:
        circuit_failure(source_key)
        raise
    circuit_success(source_key)
    return found


def filter_by_age(jobs: list, max_age_days: int = 0) -> list:
    """Filtro de antiguedad (el que usan REST y scheduler)."""
    from app.scraper.base import filter_by_max_age

    return filter_by_max_age(jobs, max_age_days)


def filter_by_fit(jobs: list, config: dict | None = None) -> tuple[list, dict]:
    """Filtro de ajuste oferta<->config (seniority, experiencia,
    salario, contrato) sobre titulo+descripcion. Sin config no filtra.

    Devuelve (aptas, descartadas_por_motivo). Lo usa REST, stream y
    scheduler despues de los filtros de edad/ubicacion.
    """
    from app.analysis import fit as fit_module
    from app.config import SMMLV_COP

    return fit_module.apply_fit(jobs, config or {}, SMMLV_COP)


def filter_batch(jobs: list, location=None,
                 max_age_days: int = 0) -> list:
    """Filtro por lote del stream (ubicacion + edad, como hasta ahora)."""
    from app.scraper.base import filter_by_location
    from app.scraper.base import filter_by_max_age

    batch = filter_by_location(jobs, location)
    return filter_by_max_age(batch, max_age_days)


def save_batch(db, jobs: list, search_query=None, uid=None,
               email=None, search_profile_id=None) -> list:
    """Passthrough a job_service.save_jobs (dedup intacto)."""
    from app.services.job_service import save_jobs

    return save_jobs(db, jobs, search_query=search_query,
                     search_profile_id=search_profile_id,
                     uid=uid, email=email)


def analyze_batch(db, scraper, profile: dict, rows: list,
                  max_details: int = 10, delay: float = 0,
                  uid=None, email=None) -> dict:
    """Passthrough a discovery.enrich_and_analyze."""
    from app.analysis.discovery import enrich_and_analyze

    return enrich_and_analyze(
        db, scraper=scraper, profile=profile, rows=rows,
        max_details=max_details, delay=delay, uid=uid, email=email,
    )
