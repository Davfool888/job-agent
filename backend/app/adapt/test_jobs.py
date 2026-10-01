"""Ofertas ficticias A/B/C para probar Adaptar-perfil (FASE 12).

URLs estables en example.com: el dedup las reutiliza sin duplicar y
jamas tocan scrapers reales.
"""
from __future__ import annotations

TEST_JOBS: tuple[dict, ...] = (
    {
        "key": "A",
        "title": "Analista de Datos Junior",
        "company": "DataCorp Colombia",
        "location": "Bogotá",
        "url": "https://example.com/adapt-test-a",
        "description": (
            "Buscamos un profesional junior para análisis de datos, "
            "generación de reportes, construcción de dashboards y "
            "automatización de procesos."),
        "skills": ["Python", "SQL", "Power BI", "Excel", "Pandas"],
        # requirements persiste en BD (skills no tiene columna): duplica
        # la lista para que el matching la vea tras el guardado.
        "requirements": ["Python", "SQL", "Power BI", "Excel", "Pandas"],
        "source": "computrabajo",
    },
    {
        "key": "B",
        "title": "Python Backend Developer Junior",
        "company": "TechSolutions",
        "location": "Medellín",
        "url": "https://example.com/adapt-test-b",
        "description": (
            "Buscamos desarrollador junior para construcción de APIs, "
            "integración de servicios y desarrollo backend utilizando "
            "Python."),
        "skills": ["Python", "FastAPI", "REST API", "PostgreSQL", "Git"],
        "requirements": ["Python", "FastAPI", "REST API", "PostgreSQL",
                         "Git"],
        "source": "computrabajo",
    },
    {
        "key": "C",
        "title": "Business Intelligence Analyst",
        "company": "Retail Analytics",
        "location": "Bogotá",
        "url": "https://example.com/adapt-test-c",
        "description": (
            "Buscamos profesional para construcción de dashboards, "
            "análisis de indicadores y generación de reportes para áreas "
            "comerciales y operativas."),
        "skills": ["Power BI", "DAX", "Excel", "SQL", "Data Visualization"],
        "requirements": ["Power BI", "DAX", "Excel", "SQL",
                         "Data Visualization"],
        "source": "computrabajo",
    },
)


def ensure_adapt_test_jobs(db) -> list:
    """Crea las 3 ofertas si no existen (idempotente por URL)."""
    from app.services.job_service import get_job_by_url, save_jobs

    saved = []
    for job in TEST_JOBS:
        existing = get_job_by_url(db, job["url"])
        if existing is not None:
            saved.append(existing)
            continue
        saved.extend(save_jobs(db, [dict(job)], search_query="adapt-test"))
    return saved
