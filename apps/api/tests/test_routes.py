from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_stub():
    response = client.post("/api/v1/auth/register")
    assert response.status_code == 201
    assert response.json()["message"].startswith("registration")


def test_assistance_returns_503_when_ai_unavailable(monkeypatch):
    async def unavailable() -> bool:
        return False

    monkeypatch.setattr("app.api.routes.assistance.ai_service_available", unavailable)
    response = client.post("/api/v1/assistance/requests", json={"description": "I need help with rent this month"})
    assert response.status_code == 503


def test_dashboard_insights():
    response = client.get("/api/v1/dashboard/community-insights")
    assert response.status_code == 200
    assert "families_assisted" in response.json()["totals"]