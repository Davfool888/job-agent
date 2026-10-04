from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200

    assert response.json()["status"] == "running"


def test_health():
    response = client.get("/health")

    assert response.status_code == 200

    assert response.json()["status"] == "ok"


def test_search_route_not_captured_as_job_id():
    # /jobs/search debe existir como ruta propia, no caer en /jobs/{job_id}.
    # Fase 1: con include_router, app.routes contiene _IncludedRouter;
    # se expanden via original_router.
    paths = []
    for r in app.routes:
        if hasattr(r, "path"):
            paths.append(r.path)
        elif hasattr(r, "original_router"):
            paths.extend(sr.path for sr in r.original_router.routes
                         if hasattr(sr, "path"))
    assert "/jobs/search" in paths
    assert "/jobs/{job_id}" in paths
