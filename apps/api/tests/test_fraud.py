"""Fraud screening: seeded abuse is flagged, submissions are never blocked.

Phase 7's exit gate: "fraud rules demonstrably flag seeded abuse cases."
Each test seeds one abuse pattern (a near-duplicate submission, an
account burst) and asserts the matching rule recorded a flag for human
review — while the case itself still reached the queue, because screening
is flag-only by design.
"""

from __future__ import annotations

from app.db.session import SessionFactory
from app.repositories.audit import verify_chain
from tests import factories

API = "/api/v1"

# Five genuinely different requests: their token sets barely overlap, so a
# burst run over these provokes only the velocity rule, not duplicates.
DISTINCT_REQUESTS = [
    "The borehole pump broke again and the whole street has no water",
    "School fees are due Friday or the children will be sent home",
    "My mother's malaria medication ran out at the clinic yesterday",
    "The rented room partially collapsed after last night's rain storm",
    "We have not eaten since morning and the children are very hungry",
]

DUPLICATE_TEXT = (
    "We need help paying rent this month, the landlord threatens eviction"
)
DUPLICATE_REWORDING = (
    "We need help with paying rent this month, the landlord threatens eviction"
)


def _stub_ai(monkeypatch) -> None:
    async def _available() -> bool:
        return True

    async def _classify(text: str) -> dict:
        return {"category": "housing", "urgency_score": 72, "priority": "high"}

    monkeypatch.setattr("app.api.routes.assistance.ai_service_available", _available)
    monkeypatch.setattr("app.api.routes.assistance.classify_need", _classify)


async def _new_org() -> int:
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        return org.id


def _submit(client, headers, org_id: int, description: str):
    return client.post(
        f"{API}/assistance/requests",
        json={"organization_id": org_id, "description": description},
        headers=headers,
    )


async def test_near_duplicate_submission_is_flagged_not_blocked(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    headers = login(user)

    first = _submit(client, headers, org_id, DUPLICATE_TEXT)
    assert first.status_code == 201, first.text

    second = _submit(client, headers, org_id, DUPLICATE_REWORDING)
    # Flag-only: the case still reaches the handlers' queue.
    assert second.status_code == 201, second.text

    leader = await make_user("faith_leader", organization_id=org_id)
    flags = client.get(f"{API}/fraud/flags", headers=login(leader))
    assert flags.status_code == 200, flags.text
    rows = flags.json()
    assert len(rows) == 1, rows
    flag = rows[0]
    assert flag["rule"] == "duplicate_request"
    assert flag["severity"] == "high"
    assert flag["status"] == "open"
    assert flag["request_id"] == second.json()["id"]
    assert str(first.json()["id"]) in flag["detail"]


async def test_submission_burst_is_flagged(client, make_user, login, monkeypatch):
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    headers = login(user)

    ids = []
    for description in DISTINCT_REQUESTS:
        response = _submit(client, headers, org_id, description)
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])

    leader = await make_user("faith_leader", organization_id=org_id)
    rows = client.get(
        f"{API}/fraud/flags?rule=submission_burst", headers=login(leader)
    ).json()
    assert len(rows) == 1, rows
    flag = rows[0]
    assert flag["rule"] == "submission_burst"
    # The threshold counts this submission too: the fifth one trips it.
    assert flag["request_id"] == ids[-1]
    assert "5 submissions" in flag["detail"]


async def test_flags_are_scoped_to_their_organization(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    org_a = await _new_org()
    org_b = await _new_org()
    user_a = await make_user("community_member", organization_id=org_a)
    _submit(client, login(user_a), org_a, DUPLICATE_TEXT)
    _submit(client, login(user_a), org_a, DUPLICATE_REWORDING)

    leader_b = await make_user("faith_leader", organization_id=org_b)
    rows = client.get(f"{API}/fraud/flags", headers=login(leader_b)).json()
    assert rows == []


async def test_reviewer_dismisses_flag_and_audit_chain_survives(
    client, make_user, login, monkeypatch
):
    _stub_ai(monkeypatch)
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    headers = login(user)
    _submit(client, headers, org_id, DUPLICATE_TEXT)
    _submit(client, headers, org_id, DUPLICATE_REWORDING)

    leader = await make_user("faith_leader", organization_id=org_id)
    leader_headers = login(leader)
    flag_id = client.get(f"{API}/fraud/flags", headers=leader_headers).json()[0]["id"]

    dismissed = client.patch(
        f"{API}/fraud/flags/{flag_id}",
        json={"status": "dismissed"},
        headers=leader_headers,
    )
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json()["status"] == "dismissed"

    reopened = client.patch(
        f"{API}/fraud/flags/{flag_id}",
        json={"status": "open"},
        headers=leader_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"

    # The reviewer's decisions joined the tamper-evident trail.
    async with SessionFactory() as session:
        assert await verify_chain(session) == []

    # A case handler from another org cannot touch it.
    other_leader = await make_user("faith_leader", organization_id=await _new_org())
    forbidden = client.patch(
        f"{API}/fraud/flags/{flag_id}",
        json={"status": "confirmed"},
        headers=login(other_leader),
    )
    assert forbidden.status_code == 403


async def test_flag_review_denied_to_non_handlers(client, make_user, login):
    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)
    assert (
        client.get(f"{API}/fraud/flags", headers=login(member)).status_code == 403
    )
    donor = await make_user("donor", organization_id=org_id)
    assert client.patch(
        f"{API}/fraud/flags/1", json={"status": "confirmed"}, headers=login(donor)
    ).status_code == 403


async def test_unknown_flag_is_404(client, make_user, login):
    org_id = await _new_org()
    leader = await make_user("faith_leader", organization_id=org_id)
    response = client.patch(
        f"{API}/fraud/flags/9999",
        json={"status": "dismissed"},
        headers=login(leader),
    )
    assert response.status_code == 404
