"""Phase 3 program directory: CRUD, org scoping and soft retirement.

Programs are the "supply side" of donor matching (PRD §20, §21): faith
leaders create and maintain their organization's programs, a donor browses
only active ones, and the matching endpoint only ever sees active programs.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Program
from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"


async def _leader_org_pair(make_user) -> tuple:
    """A faith leader plus the id of the organization they belong to."""
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        org_id = org.id
    leader = await make_user("faith_leader", organization_id=org_id)
    return leader, org_id


async def test_leader_creates_program_in_own_org(client, make_user, login):
    leader, org_id = await _leader_org_pair(make_user)
    response = client.post(
        f"{API}/programs/",
        headers=login(leader),
        json={
            "organization_id": org_id,
            "name": "School Fees Grant",
            "category": "education",
            "description": "Covers tuition for one term.",
            "location": "Nairobi",
            "budget_needed": 120000,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["organization_id"] == org_id
    assert body["name"] == "School Fees Grant"
    assert body["category"] == "education"
    assert body["is_active"] is True
    assert body["budget_needed"] == 120000


async def test_leader_cannot_create_program_for_another_org(client, make_user, login):
    async with SessionFactory() as session:
        other_org = await factories.create_organization(session)
        await session.commit()
        other_id = other_org.id
    leader, org_id = await _leader_org_pair(make_user)
    assert org_id != other_id

    response = client.post(
        f"{API}/programs/",
        headers=login(leader),
        json={"organization_id": other_id, "name": "Sneaky", "category": "food"},
    )
    assert response.status_code == 403


async def test_orgless_leader_cannot_create_program(client, make_user, login):
    leader = await make_user("faith_leader")  # no organization
    response = client.post(
        f"{API}/programs/",
        headers=login(leader),
        json={"organization_id": 1, "name": "Wayward", "category": "food"},
    )
    assert response.status_code == 403


async def test_member_cannot_create_program(client, make_user, login):
    member = await make_user("community_member")
    response = client.post(
        f"{API}/programs/",
        headers=login(member),
        json={"organization_id": 1, "name": "Hijack", "category": "food"},
    )
    assert response.status_code == 403


async def test_donor_browses_only_active_programs(client, make_user, login):
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        active = await factories.create_program(session, organization=org, name="Active Food Pantry")
        await factories.create_program(
            session, organization=org, name="Retired Shelter", is_active=False
        )
        await session.commit()
        active_id = active.id

    donor = await make_user("donor")
    response = client.get(f"{API}/programs/", headers=login(donor))
    assert response.status_code == 200, response.text
    names = [item["name"] for item in response.json()]
    assert names == ["Active Food Pantry"]
    assert active_id in [item["id"] for item in response.json()]


async def test_leader_sees_only_own_org_programs(client, make_user, login):
    async with SessionFactory() as session:
        org_a = await factories.create_organization(session)
        org_b = await factories.create_organization(session)
        await factories.create_program(
            session, organization=org_a, name="Org A Program"
        )
        await factories.create_program(
            session, organization=org_b, name="Org B Program"
        )
        await session.commit()
        org_a_id = org_a.id

    leader = await make_user("faith_leader", organization_id=org_a_id)
    response = client.get(f"{API}/programs/", headers=login(leader))
    assert response.status_code == 200, response.text
    assert [item["name"] for item in response.json()] == ["Org A Program"]


async def test_leader_can_soft_retire_own_program(client, make_user, login):
    leader, org_id = await _leader_org_pair(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        program = await factories.create_program(
            session, organization=org, name="Rent Bridge"
        )
        await session.commit()
        program_id = program.id

    response = client.patch(
        f"{API}/programs/{program_id}",
        headers=login(leader),
        json={"is_active": False, "description": "Paused for the season"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_active"] is False
    assert response.json()["description"] == "Paused for the season"

    async with SessionFactory() as session:
        row = await session.get(Program, program_id)
        assert row is not None and row.is_active is False


async def test_leader_cannot_patch_another_orgs_program(client, make_user, login):
    async with SessionFactory() as session:
        other_org = await factories.create_organization(session)
        program = await factories.create_program(
            session, organization=other_org, name="Not Yours"
        )
        await session.commit()
        program_id = program.id
    leader, _ = await _leader_org_pair(make_user)

    response = client.patch(
        f"{API}/programs/{program_id}", headers=login(leader), json={"is_active": False}
    )
    assert response.status_code == 403


async def test_admin_sees_all_programs_across_orgs(client, make_user, login):
    async with SessionFactory() as session:
        org_a = await factories.create_organization(session)
        org_b = await factories.create_organization(session)
        await factories.create_program(session, organization=org_a, name="From A")
        await factories.create_program(session, organization=org_b, name="From B")
        await session.commit()

    admin = await make_user("admin")
    response = client.get(f"{API}/programs/", headers=login(admin))
    assert response.status_code == 200, response.text
    assert {item["name"] for item in response.json()} == {"From A", "From B"}


async def test_program_creation_is_audited(client, make_user, login):
    leader, org_id = await _leader_org_pair(make_user)
    response = client.post(
        f"{API}/programs/",
        headers=login(leader),
        json={"organization_id": org_id, "name": "Audited Program", "category": "food"},
    )
    assert response.status_code == 201

    async with SessionFactory() as session:
        from app.db.models import AuditLog

        actions = (
            await session.execute(
                select(AuditLog.action).where(
                    AuditLog.action.in_(["program.created", "program.updated"])
                )
            )
        ).scalars().all()
        assert "program.created" in actions