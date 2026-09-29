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
    routes = [r.path for r in app.routes]
    assert "/jobs/search" in routes
    assert "/jobs/{job_id}" in routes
