"""Fase 0: congelar contrato API.

Estos tests no prueban lógica de negocio, solo que las rutas
críticas (buscador y PDF) siguen existiendo con mismo path y
método después de cada refactorización. Si alguno falla tras
mover código a routers, la modularización rompió el contrato.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Rutas que el frontend usa y NO pueden cambiar de path/método.
REQUIRED_ROUTES = [
    ("GET", "/health"),
    ("GET", "/health/detailed"),
    ("GET", "/jobs/search"),
    ("GET", "/jobs/search/stream"),
    ("GET", "/jobs/{job_id}"),
    ("GET", "/jobs/{job_id}/analysis"),
    ("GET", "/jobs/{job_id}/detail"),
    ("POST", "/jobs/{job_id}/analyze"),
    ("POST", "/jobs/{job_id}/adapt-cv/start"),
    ("GET", "/jobs/{job_id}/adapt-cv/status"),
    ("GET", "/jobs/{job_id}/adapt-cv/download"),
    ("POST", "/jobs/{job_id}/cv"),
    ("GET", "/jobs/{job_id}/cv"),
    ("GET", "/jobs/{job_id}/customized-cv"),
    ("GET", "/jobs/{job_id}/cv/download"),
    ("POST", "/jobs/discover"),
    ("POST", "/search-profiles/{profile_id}/run"),
    ("GET", "/scheduler/status"),
    ("POST", "/scheduler/tick"),
    ("GET", "/scheduler/jobs"),
    ("GET", "/scheduler/jobs/{job_id}"),
    ("POST", "/profile/import-pdf"),
    ("GET", "/search-config"),
    ("PUT", "/search-config"),
    ("GET", "/search-config/options"),
    ("GET", "/ai-keys/providers"),
    ("GET", "/ai-keys/status"),
    ("PUT", "/ai-keys/{provider}"),
    ("DELETE", "/ai-keys/{provider}"),
]


def _route_list():
    """Expande app.routes incluyendo _IncludedRouter (Fase 1)."""
    out = []
    for r in app.routes:
        if hasattr(r, "path"):
            out.append((r.path, "".join(sorted(r.methods))))
        elif hasattr(r, "original_router"):
            out.extend(
                (sr.path, "".join(sorted(sr.methods)))
                for sr in r.original_router.routes
                if hasattr(sr, "path")
            )
    return out


def _route_set():
    return set(_route_list())


def test_contrato_rutas_criticas():
    routes = _route_set()
    for method, path in REQUIRED_ROUTES:
        assert (path, method) in routes, f"falta ruta {method} {path}"


def test_search_antes_que_job_id():
    # /jobs/search debe declararse antes que /jobs/{job_id} o
    # FastAPI la capturaría como job_id="search".
    # Con routers, el orden es por include_router: discovery antes que jobs.
    paths = [p for p, _ in _route_list()]
    assert paths.index("/jobs/search") < paths.index("/jobs/{job_id}")
    assert paths.index("/jobs/search/stream") < paths.index("/jobs/{job_id}")


def test_health_detailed_no_500():
    r = client.get("/health/detailed")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "db_backend" in body
    assert "chromium" in body
    assert "pdflatex" in body
    assert "scheduler" in body
    # Semáforo de persistencia: backend + alcanzabilidad real.
    database = body["database"]
    assert database["backend"] == body["db_backend"]
    assert database["reachable"] is True
    if database["backend"] == "sqlite":
        assert "url" in database


def test_openapi_incluye_buscador_y_pdf():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/jobs/search" in paths
    assert "/jobs/search/stream" in paths
    assert "/jobs/{job_id}/adapt-cv/start" in paths
    assert "/health/detailed" in paths


def test_modulos_criticos_importan():
    """Los imports lazy ocultan SyntaxError hasta ejecucion: este test
    importa directo cada modulo del pipeline de busqueda."""
    import app.adapt.content  # noqa: F401
    import app.adapt.service  # noqa: F401
    import app.analysis.fit  # noqa: F401
    import app.routers.discovery  # noqa: F401
    import app.routers.search_profiles  # noqa: F401
    import app.scheduler  # noqa: F401
    import app.services.run_queue  # noqa: F401
    import app.services.search_config  # noqa: F401
    import app.services.search_orchestrator  # noqa: F401
    import app.services.search_profiles  # noqa: F401
