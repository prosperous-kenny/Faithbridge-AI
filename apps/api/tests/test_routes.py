async def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_register_reaches_the_auth_handler(client, clean_db):
    """Registration is implemented now: a valid payload gets a 201, not a stub."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "routes-check@example.org",
            "password": "correct-horse-1",
            "full_name": "Routes Check",
            "role": "community_member",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "community_member"


async def test_assistance_returns_503_when_ai_unavailable(
    client, make_user, monkeypatch
):
    async def unavailable() -> bool:
        return False

    monkeypatch.setattr("app.api.routes.assistance.ai_service_available", unavailable)

    # The org must exist so the request reaches the AI boundary; org validation
    # is now checked first and would otherwise mask the fail-closed 503.
    from app.db.session import SessionFactory
    from tests import factories

    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        org_id = org.id

    admin = await make_user("admin")
    response = client.post(
        "/api/v1/assistance/requests",
        json={
            "organization_id": org_id,
            "description": "I need help with rent this month",
        },
        headers=_bearer(admin),
    )
    assert response.status_code == 503


async def test_dashboard_stats_is_guarded(client, clean_db):
    """Anonymous callers get 401 before any counting happens."""
    response = client.get("/api/v1/dashboard/stats")
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


async def test_dashboard_stats_returns_counts(client, make_user):
    admin = await make_user("admin")
    response = client.get("/api/v1/dashboard/stats", headers=_bearer(admin))
    assert response.status_code == 200
    body = response.json()
    assert "assistance_requests" in body
    assert "donations" in body
    assert all(isinstance(v, int) for v in body.values())


def _bearer(user) -> dict[str, str]:
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}
