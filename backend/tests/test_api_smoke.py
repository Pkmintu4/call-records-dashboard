from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def _client() -> TestClient:
    settings.auto_ingest_enabled = False
    return TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    with _client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingest_status_endpoint_returns_shape() -> None:
    with _client() as client:
        response = client.get("/api/ingest/status")

    assert response.status_code == 200
    payload = response.json()
    assert "running" in payload
    assert "current" in payload
    assert "last_result" in payload


def test_dashboard_smoke_endpoints_return_200() -> None:
    endpoints = [
        "/api/dashboard/distribution",
        "/api/dashboard/overall-kpis",
        "/api/dashboard/calls?limit=1",
        "/api/dashboard/search?q=school&limit=1",
    ]

    with _client() as client:
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200, f"Expected 200 for {endpoint}, got {response.status_code}"


def test_google_auth_url_endpoint_responds() -> None:
    with _client() as client:
        response = client.get("/api/google/auth-url")

    assert response.status_code == 200
    payload = response.json()
    assert "auth_mode" in payload
    assert "requires_user_auth" in payload
