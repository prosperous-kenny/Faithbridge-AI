"""Phase 4 donation ledger: pledge creation, the PRD §8 lifecycle, allocation
rules, org scoping and the audit + impact writes around money moving.

The lifecycle is ``pledged → paid → allocated → distributed``. Donors can only
pledge and read their own rows; only the receiving organization's faith leader
(or the platform admin) advances a donation. Allocation is where the rules
bite: a target beneficiary is required, must exist, and must belong to the
same organization as the money.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import AuditLog, Donation, ImpactEvent
from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"


async def _donor(client, make_user, login) -> tuple:
    donor = await make_user("donor")
    headers = login(donor)
    return donor, headers


async def _org_and_leader(make_user) -> tuple:
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        org_id = org.id
    leader = await make_user("faith_leader", organization_id=org_id)
    return org_id, leader


async def _distributed_donation(client, make_user, login, amount=5000):
    """Walk a pledge all the way through the lifecycle and return its id."""
    donor = await make_user("donor")
    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        _, beneficiary, _ = await factories.create_assistance_request(
            session, organization=org
        )
        await session.commit()
        beneficiary_id = beneficiary.id

    pledge = client.post(
        f"{API}/donations/",
        headers=login(donor),
        json={"organization_id": org_id, "amount": amount, "currency": "USD"},
    )
    assert pledge.status_code == 201, pledge.text
    donation_id = pledge.json()["id"]

    leader_headers = login(leader)
    paid = client.patch(
        f"{API}/donations/{donation_id}/status",
        headers=leader_headers,
        json={"status": "paid"},
    )
    assert paid.status_code == 200, paid.text
    allocated = client.patch(
        f"{API}/donations/{donation_id}/status",
        headers=leader_headers,
        json={"status": "allocated", "beneficiary_id": beneficiary_id},
    )
    assert allocated.status_code == 200, allocated.text
    distributed = client.patch(
        f"{API}/donations/{donation_id}/status",
        headers=leader_headers,
        json={"status": "distributed"},
    )
    assert distributed.status_code == 200, distributed.text
    return donation_id, org_id, leader, beneficiary_id, donor


async def test_donor_creates_a_pledge(client, make_user, login):
    _, headers = await _donor(client, make_user, login)
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        org_id = org.id

    response = client.post(
        f"{API}/donations/",
        headers=headers,
        json={"organization_id": org_id, "amount": 7500, "currency": "USD"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pledged"
    assert body["amount"] == 7500
    assert body["paid_at"] is None


async def test_donor_cannot_pledge_to_missing_organization(client, make_user, login):
    _, headers = await _donor(client, make_user, login)
    response = client.post(
        f"{API}/donations/", headers=headers, json={"organization_id": 9999, "amount": 100}
    )
    assert response.status_code == 404


async def test_donor_cannot_advance_a_donation(client, make_user, login):
    donation_id, _, _, _, donor = await _distributed_donation(client, make_user, login)
    # A new donor (never the money's handler) must not be able to move it.
    other_donor, headers = await _donor(client, make_user, login)
    assert other_donor.id != donor.id
    response = client.patch(
        f"{API}/donations/{donation_id}/status", headers=headers, json={"status": "paid"}
    )
    assert response.status_code == 403


async def test_leader_cannot_advance_another_orgs_donation(client, make_user, login):
    async with SessionFactory() as session:
        org_a = await factories.create_organization(session)
        org_b = await factories.create_organization(session)
        donor = await factories.create_linked_user(session, email="pledger@example.org", role="donor")
        await factories.create_donation(session, donor=donor, organization=org_a)
        await session.commit()
        donation_id = (await session.execute(select(Donation).order_by(Donation.id.desc()).limit(1))).scalar_one().id

    leader_b = await make_user("faith_leader", organization_id=org_b.id)
    response = client.patch(
        f"{API}/donations/{donation_id}/status",
        headers=login(leader_b),
        json={"status": "paid"},
    )
    assert response.status_code == 403


async def test_lifecycle_rejects_illegal_transitions(client, make_user, login):
    donor = await make_user("donor")
    org_id, leader = await _org_and_leader(make_user)
    pledge = client.post(
        f"{API}/donations/",
        headers=login(donor),
        json={"organization_id": org_id, "amount": 2000},
    )
    donation_id = pledge.json()["id"]

    response = client.patch(
        f"{API}/donations/{donation_id}/status",
        headers=login(leader),
        json={"status": "distributed"},
    )
    assert response.status_code == 409
    assert "pledged -> distributed" in response.json()["detail"]


async def test_allocation_requires_a_target_beneficiary(client, make_user, login):
    donor = await make_user("donor")
    org_id, leader = await _org_and_leader(make_user)
    pledge = client.post(
        f"{API}/donations/",
        headers=login(donor),
        json={"organization_id": org_id, "amount": 2000},
    )
    donation_id = pledge.json()["id"]
    leader_headers = login(leader)
    assert client.patch(
        f"{API}/donations/{donation_id}/status", headers=leader_headers, json={"status": "paid"}
    ).status_code == 200

    response = client.patch(
        f"{API}/donations/{donation_id}/status",
        headers=leader_headers,
        json={"status": "allocated", "beneficiary_id": None},
    )
    assert response.status_code == 422


async def test_allocation_rejects_beneficiary_from_another_org(client, make_user, login):
    donor = await make_user("donor")
    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        other_org = await factories.create_organization(session)
        _, beneficiary, _ = await factories.create_assistance_request(
            session, organization=other_org
        )
        donation = await factories.create_donation(
            session, donor=donor, organization=await session.get(factories.Organization, org_id)
        )
        await session.commit()
        donation_id = donation.id
        beneficiary_id = beneficiary.id

    leader_headers = login(leader)
    assert client.patch(
        f"{API}/donations/{donation_id}/status", headers=leader_headers, json={"status": "paid"}
    ).status_code == 200

    response = client.patch(
        f"{API}/donations/{donation_id}/status",
        headers=leader_headers,
        json={"status": "allocated", "beneficiary_id": beneficiary_id},
    )
    assert response.status_code == 422
    assert "same organization" in response.json()["detail"]


async def test_full_lifecycle_sets_timestamps_and_distributes(client, make_user, login):
    donation_id, _, _, _, _ = await _distributed_donation(client, make_user, login)
    async with SessionFactory() as session:
        donation = await session.get(Donation, donation_id)
        assert donation.status == "distributed"
        assert donation.paid_at is not None
        assert donation.allocated_at is not None
        assert donation.distributed_at is not None
        assert donation.allocated_to_beneficiary_id is not None


async def test_distribution_writes_impact_event_and_audit(client, make_user, login):
    _, org_id, _, _, _ = await _distributed_donation(
        client, make_user, login, amount=10000
    )
    async with SessionFactory() as session:
        event = (
            await session.execute(
                select(ImpactEvent).where(ImpactEvent.metric == "donations_distributed")
            )
        ).scalar_one()
        assert event.organization_id == org_id
        assert event.value == 10000

        actions = (
            await session.execute(select(AuditLog.action))
        ).scalars().all()
        assert "donation.pledged" in actions
        assert "donation.status.paid" in actions
        assert "donation.status.allocated" in actions
        assert "donation.status.distributed" in actions


async def test_donor_sees_only_own_ledger(client, make_user, login):
    donor_a = await make_user("donor")
    donor_b = await make_user("donor")
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await factories.create_donation(session, donor=donor_a, organization=org, amount=111)
        await factories.create_donation(session, donor=donor_b, organization=org, amount=222)
        await session.commit()

    response = client.get(f"{API}/donations/", headers=login(donor_a))
    assert response.status_code == 200, response.text
    amounts = [item["amount"] for item in response.json()["items"]]
    assert amounts == [111]