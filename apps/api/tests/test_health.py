from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_ok():
    with TestClient(app) as c:
        response = c.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_reports_database_up():
    with TestClient(app) as c:
        response = c.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "up"
