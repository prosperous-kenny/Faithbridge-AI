"""Phase 5 privacy: explicit consent recording and data-deletion requests (PRD §22).

Consent is the gate every PII renderer reads (``beneficiaries.consented_at``);
this surface captures it explicitly, either self-service or captured by a case
handler. Deletion is a governed workflow, never a raw DELETE: the request is
recorded tamper-evidently and later resolved by an administrator.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import AuditLog, Beneficiary, DeletionRequest
from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"


async def _org_leader_and_beneficiary(make_user, *, org=None):
    """An org, its leader, and a beneficiary (with linked user) in that org."""
    async with SessionFactory() as session:
        org = org or await factories.create_organization(session)
        _, beneficiary, beneficiary_user = await factories.create_assistance_request(
            session, organization=org, consented=False
        )
        await session.commit()
        beneficiary_id = beneficiary.id
    leader = await make_user("faith_leader", organization_id=org.id)
    return org, leader, beneficiary_id, beneficiary_user


async def test_self_service_consent_sets_gate_and_audits(client, make_user, login):
    _, _, beneficiary_id, _linked = await _org_leader_and_beneficiary(make_user)
    # The linked person above was created by a factory without a password; to
    # exercise the self-service path we make a real account and point a
    # beneficiary row at it.
    member = await make_user("community_member")
    async with SessionFactory() as session:
        beneficiary = await session.get(Beneficiary, beneficiary_id)
        beneficiary.user_id = member.id
        beneficiary.consented_at = None
        await session.commit()

    response = client.post(f"{API}/privacy/consent", headers=login(member))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["beneficiary_id"] == beneficiary_id
    assert body["consented_at"] is not None

    async with SessionFactory() as session:
        updated = await session.get(Beneficiary, beneficiary_id)
        assert updated.consented_at is not None
        actions = (await session.execute(select(AuditLog.action))).scalars().all()
        assert "privacy.consent.recorded" in actions


async def test_self_service_consent_needs_a_beneficiary(client, make_user, login):
    member = await make_user("community_member")
    async with SessionFactory() as session:
        await factories.create_organization(session)
        await session.commit()
    response = client.post(f"{API}/privacy/consent", headers=login(member))
    assert response.status_code == 404


async def test_handler_records_consent_on_behalf(client, make_user, login):
    _org, leader, beneficiary_id, _ = await _org_leader_and_beneficiary(make_user)
    response = client.post(
        f"{API}/privacy/consent/{beneficiary_id}", headers=login(leader)
    )
    assert response.status_code == 200, response.text
    assert response.json()["consented_at"] is not None

    # A leader from another org must not be able to consent their neighbour's people.
    async with SessionFactory() as session:
        other_org = await factories.create_organization(session)
        await session.commit()
    outsider = await make_user("faith_leader", organization_id=other_org.id)
    blocked = client.post(
        f"{API}/privacy/consent/{beneficiary_id}", headers=login(outsider)
    )
    assert blocked.status_code == 403


async def test_self_service_data_deletion_request(client, make_user, login):
    donor = await make_user("donor")
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        org_id = org.id
    async with SessionFactory() as session:
        org_obj = await session.get(factories.Organization, org_id)
        _m, beneficiary, _u = await factories.create_assistance_request(session, organization=org_obj)
        await session.commit()
        beneficiary_id = beneficiary.id
    async with SessionFactory() as session:
        beneficiary = await session.get(Beneficiary, beneficiary_id)
        beneficiary.user_id = donor.id
        await session.commit()

    response = client.post(
        f"{API}/privacy/data-deletion",
        headers=login(donor),
        json={"scope": "donor", "reason": "leaving the platform"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scope"] == "donor"
    assert body["status"] == "pending"

    async with SessionFactory() as session:
        request = await session.get(DeletionRequest, body["id"])
        assert request.requester_id == donor.id
        assert request.beneficiary_id == beneficiary_id


async def test_handler_requests_deletion_for_beneficiary(client, make_user, login):
    _org, leader, beneficiary_id, _ = await _org_leader_and_beneficiary(make_user)
    response = client.post(
        f"{API}/privacy/data-deletion/{beneficiary_id}",
        headers=login(leader),
        json={"scope": "beneficiary", "reason": "moved away"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["beneficiary_id"] == beneficiary_id

    async with SessionFactory() as session:
        actions = (await session.execute(select(AuditLog.action))).scalars().all()
        assert "privacy.deletion.requested" in actions


async def test_deletion_inbox_scoped_to_org_and_role(client, make_user, login):
    org_a, leader_a, beneficiary_a, _ = await _org_leader_and_beneficiary(make_user)
    async with SessionFactory() as session:
        org_b = await factories.create_organization(session, name="Other Church")
        _, beneficiary_b, _ = await factories.create_assistance_request(
            session, organization=org_b, consented=False
        )
        await session.commit()
        org_b_id = org_b.id
        beneficiary_b_id = beneficiary_b.id
    leader_b = await make_user("faith_leader", organization_id=org_b_id)

    client.post(
        f"{API}/privacy/data-deletion/{beneficiary_a}",
        headers=login(leader_a),
        json={"scope": "beneficiary"},
    )
    client.post(
        f"{API}/privacy/data-deletion/{beneficiary_b_id}",
        headers=login(leader_b),
        json={"scope": "beneficiary"},
    )

    inbox_a = client.get(f"{API}/privacy/data-deletion", headers=login(leader_a))
    assert inbox_a.status_code == 200
    assert all(item["organization_id"] == org_a.id for item in inbox_a.json()["items"])

    admin = await make_user("admin")
    inbox_admin = client.get(f"{API}/privacy/data-deletion", headers=login(admin))
    assert len(inbox_admin.json()["items"]) == 2

    donor = await make_user("donor")
    assert client.get(f"{API}/privacy/data-deletion", headers=login(donor)).status_code == 403