"""Volunteer profiles and matching (Phase 7).

Covers the registration upsert, the availability vocabulary, org scoping,
the handler-only directory, and the scoring order the matcher returns —
including the data-minimization assertion that matches carry a name and
nothing more contact-like.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Volunteer
from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"

VOLUNTEERS = [
    # user, skills, availability — designed so v1 wins on both dimensions.
    ("cook", ["cooking", "driving"], ["weekend_morning"]),
    ("plumber", ["cooking"], ["weekend_evening"]),
    ("handyman", ["plumbing"], ["weekday_morning"]),
]


async def _new_org(name: str = "Test Church") -> int:
    async with SessionFactory() as session:
        org = await factories.create_organization(session, name=name)
        await session.commit()
        return org.id


async def _register(client, login, user, org_id: int, skills, availability):
    return client.post(
        f"{API}/volunteers",
        json={
            "organization_id": org_id,
            "skills": skills,
            "availability": availability,
        },
        headers=login(user),
    )


async def test_register_then_update_is_an_upsert(client, make_user, login):
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)

    created = await _register(
        client, login, user, org_id, ["cooking", "driving"], ["weekend_morning"]
    )
    assert created.status_code == 201, created.text
    assert created.json()["skills"] == ["cooking", "driving"]
    assert created.json()["is_active"] is True

    updated = await _register(
        client, login, user, org_id, ["gardening"], ["weekday_evening"]
    )
    assert updated.status_code == 201, updated.text
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["skills"] == ["gardening"]
    assert updated.json()["availability"] == ["weekday_evening"]

    # One row, not two: the unique user constraint held.
    leader = await make_user("faith_leader", organization_id=org_id)
    directory = client.get(f"{API}/volunteers", headers=login(leader))
    assert directory.status_code == 200
    assert len(directory.json()) == 1


async def test_unknown_availability_slot_is_422(client, make_user, login):
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    response = await _register(
        client, login, user, org_id, ["cooking"], ["middle_of_the_night"]
    )
    assert response.status_code == 422
    assert "availability slots" in response.text


async def test_cross_org_registration_is_403(client, make_user, login):
    org_a = await _new_org()
    org_b = await _new_org(name="Other Church")
    user = await make_user("community_member", organization_id=org_a)
    response = await _register(
        client, login, user, org_b, ["cooking"], ["weekend_morning"]
    )
    assert response.status_code == 403


async def test_donor_may_hold_a_volunteer_profile(client, make_user, login):
    """PRD §5 volunteering spans roles: registration is open to all four."""
    org_id = await _new_org()
    donor = await make_user("donor", organization_id=org_id)
    response = await _register(
        client, login, donor, org_id, ["tutoring"], ["weekday_evening"]
    )
    assert response.status_code == 201, response.text


async def test_directory_requires_handler_role(client, make_user, login):
    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)
    assert client.get(f"{API}/volunteers", headers=login(member)).status_code == 403
    leader = await make_user("faith_leader", organization_id=org_id)
    assert client.get(f"{API}/volunteers", headers=login(leader)).status_code == 200


async def test_match_ranks_by_skill_and_availability(client, make_user, login):
    org_id = await _new_org()
    users = {}
    for tag, skills, availability in VOLUNTEERS:
        user = await make_user("community_member", organization_id=org_id)
        users[tag] = user
        response = await _register(
            client, login, user, org_id, skills, availability
        )
        assert response.status_code == 201, response.text

    leader = await make_user("faith_leader", organization_id=org_id)
    response = client.post(
        f"{API}/volunteers/match",
        json={
            "organization_id": org_id,
            "skills": ["cooking"],
            "availability": ["weekend_morning"],
        },
        headers=login(leader),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    matches = body["matches"]
    assert [m["user_id"] for m in matches] == [
        users["cook"].id,
        users["plumber"].id,
        users["handyman"].id,
    ]
    # Full coverage on both dimensions, then skills-only, then neither.
    assert [m["score"] for m in matches] == [100, 60, 0]
    assert matches[0]["matched_skills"] == ["cooking"]
    assert matches[0]["matched_availability"] == ["weekend_morning"]
    # Data minimization: name and ids, nothing contact-like (PRD §22).
    for match in matches:
        assert set(match) == {
            "volunteer_id",
            "user_id",
            "user_name",
            "skills",
            "availability",
            "score",
            "matched_skills",
            "matched_availability",
        }
        assert "email" not in str(match).lower()
        assert "@" not in str(match)


async def test_match_returns_empty_without_requirements(
    client, make_user, login
):
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    await _register(client, login, user, org_id, ["cooking"], ["weekend_morning"])
    leader = await make_user("faith_leader", organization_id=org_id)
    response = client.post(
        f"{API}/volunteers/match",
        json={"organization_id": org_id},
        headers=login(leader),
    )
    assert response.status_code == 200
    assert response.json()["matches"] == []


async def test_match_denied_to_non_handlers(client, make_user, login):
    org_id = await _new_org()
    member = await make_user("community_member", organization_id=org_id)
    response = client.post(
        f"{API}/volunteers/match",
        json={"organization_id": org_id, "skills": ["cooking"]},
        headers=login(member),
    )
    assert response.status_code == 403


async def test_inactive_volunteers_are_excluded_from_matching(
    client, make_user, login
):
    org_id = await _new_org()
    user = await make_user("community_member", organization_id=org_id)
    await _register(client, login, user, org_id, ["cooking"], ["weekend_morning"])

    async with SessionFactory() as session:
        volunteer = (
            await session.execute(
                select(Volunteer).where(Volunteer.user_id == user.id)
            )
        ).scalar_one()
        volunteer.is_active = False
        await session.commit()

    leader = await make_user("faith_leader", organization_id=org_id)
    response = client.post(
        f"{API}/volunteers/match",
        json={"organization_id": org_id, "skills": ["cooking"]},
        headers=login(leader),
    )
    assert response.status_code == 200
    assert response.json()["matches"] == []
