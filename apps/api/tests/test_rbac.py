"""Role-based access control: the four PRD §12 roles across every guarded route.

The matrix below is the executable form of the Phase 1 exit gate: a donor must
be unable to reach beneficiary PII, every protected route must reject
anonymous callers with 401, and the system administrator must supersede.
"""

from __future__ import annotations

from app.core.rbac import Role, role_permits
from app.core.security import create_access_token
from app.services.email import EmailResult

API = "/api/v1"

# method, path, and which roles the guard lets through. Anything not listed
# must be denied. "OK" means the guard passes the request on; the concrete
# status then depends on the handler (e.g. 503 when the AI service is stubbed
# off), so allowed routes are asserted as "not 403" rather than as a code.
GUARDED_ROUTES = [
    ("GET", f"{API}/assistance/requests", {"faith_leader", "admin"}),
    ("POST", f"{API}/assistance/requests", {"community_member", "faith_leader", "admin"}),
    ("GET", f"{API}/dashboard/stats", {"faith_leader", "admin"}),
    ("GET", f"{API}/donations/", {"donor", "admin"}),
    ("POST", f"{API}/notifications/email/test", {"admin"}),
    # Phase 3: programs are readable by everyone (the public directory donors
    # match against); creation/patching is deliberately not in the matrix —
    # an orgless faith leader hits the handler's own 403, which is a domain
    # guard, not a role guard. Preferences and matching are donor concerns
    # (admin supersedes per §12).
    ("GET", f"{API}/programs/", {"community_member", "donor", "faith_leader", "admin"}),
    ("GET", f"{API}/donors/preferences/", {"donor", "admin"}),
    ("PUT", f"{API}/donors/preferences/", {"donor", "admin"}),
    ("POST", f"{API}/ai/match-donors", {"donor", "admin"}),
]

ROLE_NAMES = [role.value for role in Role]


# --- the check itself ------------------------------------------------------


def test_role_permits_fails_closed_on_unknown_roles():
    assert role_permits("superuser", frozenset({Role.ADMIN})) is False
    assert role_permits("", frozenset({Role.ADMIN})) is False
    assert role_permits("ADMIN", frozenset({Role.ADMIN})) is False  # case sensitive


def test_admin_supersedes_every_allowed_role():
    """An admin satisfies a guard written for any single other role."""
    for role in Role:
        assert role_permits(Role.ADMIN.value, frozenset({role})) is True
    assert role_permits(Role.ADMIN.value, frozenset({Role.DONOR, Role.FAITH_LEADER}))


def test_non_admin_roles_grant_exactly_one_role():
    for role in Role:
        if role is Role.ADMIN:
            continue
        assert role_permits(role.value, frozenset({role})) is True
        for other in Role:
            if other is role:
                continue
            assert role_permits(role.value, frozenset({other})) is False, (
                f"{role.value} must not satisfy {other.value}"
            )


def test_role_values_match_prd_20():
    assert ROLE_NAMES == ["community_member", "donor", "faith_leader", "admin"]


# --- the matrix ------------------------------------------------------------


async def test_every_guarded_route_rejects_anonymous_callers(client, make_user):
    await make_user("admin")  # brings clean_db along, so tests start from empty
    for method, path, _ in GUARDED_ROUTES:
        kwargs = {"json": _payload_for(method, path)}
        response = client.request(method, path, **kwargs)
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
        assert response.headers.get("WWW-Authenticate") == "Bearer"


async def test_role_matrix_is_enforced(client, make_user, monkeypatch):
    _stub_ai_and_email(monkeypatch)
    users = {role: await make_user(role) for role in ROLE_NAMES}

    for method, path, allowed in GUARDED_ROUTES:
        for role in ROLE_NAMES:
            headers = _bearer(users[role])
            kwargs = {"headers": headers, "json": _payload_for(method, path)}
            response = client.request(method, path, **kwargs)

            if role in allowed:
                assert response.status_code != 403, (
                    f"{method} {path} as {role} should pass the guard but was "
                    f"denied: {response.text[:200]}"
                )
            else:
                # An authenticated caller must be told they lack permission
                # (403), not be made to look unauthenticated (401).
                assert response.status_code == 403, (
                    f"{method} {path} as {role} expected 403, got "
                    f"{response.status_code}: {response.text[:200]}"
                )


async def test_admin_reaches_every_guarded_route(client, make_user, monkeypatch):
    _stub_ai_and_email(monkeypatch)
    admin = await make_user("admin")
    headers = _bearer(admin)

    for method, path, _ in GUARDED_ROUTES:
        response = client.request(
            method, path, headers=headers, json=_payload_for(method, path)
        )
        assert response.status_code != 403, f"{method} {path} denied admin"


# --- PRD §22: donor must never reach beneficiary PII ------------------------


async def test_donor_cannot_read_assistance_requests(client, make_user, login):
    import factories

    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        request, _, _ = await factories.create_assistance_request(
            session, consented=True, linked_user=True
        )
        await session.commit()
        request_id = request.id

    donor = await make_user("donor")
    response = client.get(f"{API}/assistance/requests", headers=login(donor))

    assert response.status_code == 403
    # The denial body carries nothing but the refusal itself: no case id, no
    # description, no beneficiary, no address.
    assert set(response.json()) == {"detail"}
    assert str(request_id) not in response.text
    assert "Rent is overdue" not in response.text
    assert "@example.org" not in response.text


async def test_faith_leader_sees_pii_only_with_consent(client, make_user, login):
    import factories

    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await factories.create_assistance_request(
            session, consented=True, linked_user=True, organization=org
        )
        await factories.create_assistance_request(
            session, consented=False, linked_user=True, organization=org
        )
        await session.commit()

    leader = await make_user("faith_leader")
    response = client.get(f"{API}/assistance/requests", headers=login(leader))
    assert response.status_code == 200, response.text

    items = {item["beneficiary"]["consented"]: item for item in response.json()}
    assert set(items) == {True, False}

    consented = items[True]["beneficiary"]
    assert consented["person"] is not None
    assert consented["person"]["email"].endswith("@example.org")

    withheld = items[False]["beneficiary"]
    assert withheld["person"] is None
    # The row stays visible to a case handler, but carries no identity.
    assert "email" not in str(withheld)


async def test_admin_can_read_assistance_requests(client, make_user, login):
    import factories

    from app.db.session import SessionFactory

    async with SessionFactory() as session:
        await factories.create_assistance_request(session, consented=True, linked_user=True)
        await session.commit()

    admin = await make_user("admin")
    response = client.get(f"{API}/assistance/requests", headers=login(admin))
    assert response.status_code == 200
    assert len(response.json()) == 1


# --- donor ledger scoping ---------------------------------------------------


async def test_donor_sees_only_their_own_donations(client, make_user, login):
    import factories

    from app.db.session import SessionFactory

    donor_a = await make_user("donor", email="donor-a@example.org")
    donor_b = await make_user("donor", email="donor-b@example.org")

    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await factories.create_donation(session, donor=donor_a, amount=1000, organization=org)
        await factories.create_donation(session, donor=donor_b, amount=9999, organization=org)
        await session.commit()

    response = client.get(f"{API}/donations/", headers=login(donor_a))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count"] == 1
    assert body["items"][0]["amount"] == 1000
    assert body["items"][0]["donor_id"] == donor_a.id


async def test_admin_sees_the_whole_ledger(client, make_user, login):
    import factories

    from app.db.session import SessionFactory

    donor_a = await make_user("donor", email="donor-a@example.org")
    donor_b = await make_user("donor", email="donor-b@example.org")

    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await factories.create_donation(session, donor=donor_a, amount=1000, organization=org)
        await factories.create_donation(session, donor=donor_b, amount=9999, organization=org)
        await session.commit()

    admin = await make_user("admin")
    response = client.get(f"{API}/donations/", headers=login(admin))
    assert response.status_code == 200
    assert response.json()["count"] == 2


# --- helpers ---------------------------------------------------------------


def _bearer(user) -> dict[str, str]:
    """Mint a token directly: a failure here must mean "guard broken", not
    "login broken", so this test does not route through /auth/login."""
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _payload_for(method: str, path: str) -> dict:
    if "notifications" in path:
        return {"to": "someone@example.org", "subject": "test", "body": "hi"}
    if "preferences" in path and method == "PUT":
        return {"causes": [], "budget": 100, "location": "Lagos"}
    if "match-donors" in path:
        # No prefs are saved for these users, so the handler answers 400
        # before touching the AI service — still "not 403", which is all the
        # role matrix asserts.
        return {}
    if method == "POST":
        return {
            "organization_id": 1,
            "description": "I need help with rent this month",
        }
    return {}


def _stub_ai_and_email(monkeypatch) -> None:
    async def _unavailable() -> bool:
        return False

    async def _send_email(to, subject, body):
        return EmailResult(sent=True, detail="stubbed")

    monkeypatch.setattr("app.api.routes.assistance.ai_service_available", _unavailable)
    monkeypatch.setattr("app.api.routes.notifications.send_email", _send_email)
