"""Employment placements: the Phase 6 routes, mounted and exercised.

The employment router existed since Phase 6 but was never registered in
``main.py``, so its five endpoints were unreachable and untested. These
tests mount-proof it: create a placement, list it, and run the matcher
against a real beneficiary.
"""

from __future__ import annotations

from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"


async def _seed_beneficiary() -> tuple[int, int]:
    """One org and one consented beneficiary inside it; return their ids."""
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        _, beneficiary, _ = await factories.create_assistance_request(
            session, consented=True, linked_user=True, organization=org
        )
        await session.commit()
        return org.id, beneficiary.id


async def test_create_list_and_match_placement(client, make_user, login):
    org_id, beneficiary_id = await _seed_beneficiary()
    leader = await make_user("faith_leader", organization_id=org_id)
    headers = login(leader)

    created = client.post(
        f"{API}/employment/placements",
        json={
            "beneficiary_id": beneficiary_id,
            "employer": "Sunrise Bakery",
            "role_title": "Apprentice Baker",
            "skills": ["baking", "customer service"],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    placement = created.json()
    assert placement["status"] == "placed"
    assert placement["skills"] == ["baking", "customer service"]

    listed = client.get(f"{API}/employment/placements", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [placement["id"]]

    matched = client.post(
        f"{API}/employment/placements/match",
        json={"beneficiary_id": beneficiary_id, "limit": 5},
        headers=headers,
    )
    assert matched.status_code == 200, matched.text
    body = matched.json()
    assert body["beneficiary_id"] == beneficiary_id
    assert body["matches"] == []  # no beneficiary skills recorded to score on


async def test_placement_status_can_be_advanced(client, make_user, login):
    org_id, beneficiary_id = await _seed_beneficiary()
    leader = await make_user("faith_leader", organization_id=org_id)
    headers = login(leader)

    created = client.post(
        f"{API}/employment/placements",
        json={
            "beneficiary_id": beneficiary_id,
            "employer": "City Transit",
            "role_title": "Dispatcher Clerk",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    updated = client.patch(
        f"{API}/employment/placements/{created.json()['id']}/status",
        json={"status": "started"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "started"


async def test_placement_creation_denied_to_non_handlers(client, make_user, login):
    org_id, beneficiary_id = await _seed_beneficiary()
    member = await make_user("community_member", organization_id=org_id)
    response = client.post(
        f"{API}/employment/placements",
        json={
            "beneficiary_id": beneficiary_id,
            "employer": "Any Co",
            "role_title": "Any Role",
        },
        headers=login(member),
    )
    assert response.status_code == 403


async def test_unknown_beneficiary_is_404(client, make_user, login):
    org_id, _ = await _seed_beneficiary()
    leader = await make_user("faith_leader", organization_id=org_id)
    response = client.post(
        f"{API}/employment/placements",
        json={
            "beneficiary_id": 999999,
            "employer": "Any Co",
            "role_title": "Any Role",
        },
        headers=login(leader),
    )
    assert response.status_code == 404
