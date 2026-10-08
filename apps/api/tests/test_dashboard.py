"""Phase 5 dashboard: community insights, impact report, and CSV/PDF export.

Three properties matter here. (1) Aggregates are computed from the real rows
and stay PII-free — a donor or handler never receives a description, an email,
or a name. (2) Scope holds: a faith leader sees only their own organization,
and an admin must name one. (3) The report matches the Impact Score service
exactly, so the JSON view and the exported files cannot drift from the
measurement PRD §15 defines.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import AuditLog
from app.db.session import SessionFactory
from tests import factories

API = "/api/v1"


async def _org_and_leader(make_user):
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        org_id = org.id
    leader = await make_user("faith_leader", organization_id=org_id)
    return org_id, leader


async def test_dashboard_stats_rejects_donor(client, make_user, login):
    donor = await make_user("donor")
    response = client.get(f"{API}/dashboard/stats", headers=login(donor))
    assert response.status_code == 403


async def test_community_insights_returns_real_aggregates(client, make_user, login):
    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        donor = await factories.create_linked_user(session, email="giver@example.org", role="donor")
        _, _, _ = await factories.create_assistance_request(
            session, organization=org, category="housing", priority="critical"
        )
        _, _, _ = await factories.create_assistance_request(
            session, organization=org, category="food", priority="high"
        )
        # One fulfilled request so the trend includes a fulfilment.
        fulfilled, _, _ = await factories.create_assistance_request(
            session, organization=org, category="housing", priority="medium"
        )
        fulfilled.status = "fulfilled"

        program = await factories.create_program(session, organization=org)
        paid = await factories.create_donation(
            session, donor=donor, organization=org, program=program, amount=4000, status="paid"
        )
        paid.paid_at = paid.created_at
        distributed = await factories.create_donation(
            session, donor=donor, organization=org, program=program, amount=6000, status="distributed"
        )
        distributed.paid_at = distributed.created_at
        distributed.allocated_at = distributed.created_at
        distributed.distributed_at = distributed.created_at
        await session.commit()

    response = client.get(
        f"{API}/dashboard/community-insights", headers=login(leader)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization_id"] == org_id

    assert len(body["trends"]) == 1
    trend = body["trends"][0]
    assert trend["submitted"] == 3
    assert trend["fulfilled"] == 1
    assert trend["paid_amount"] == 10000
    assert trend["distributed_amount"] == 6000

    categories = {c["category"]: c for c in body["high_need_categories"]}
    assert categories["housing"]["open"] == 1
    assert categories["food"]["open"] == 1
    assert categories["housing"]["fulfilled"] == 1

    effectiveness = body["donation_effectiveness"]
    assert effectiveness["paid_amount"] == 10000
    assert effectiveness["distributed_amount"] == 6000
    assert effectiveness["per_program"][0]["distributed_amount"] == 6000


async def test_community_insights_response_is_pii_free(client, make_user, login):
    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        request, _, _ = await factories.create_assistance_request(
            session,
            organization=org,
            linked_user=True,
        )
        request.description = "Rent overdue for the Smith family at 12 Example Street"
        await session.commit()

    response = client.get(
        f"{API}/dashboard/community-insights", headers=login(leader)
    )
    assert response.status_code == 200
    body = str(response.json())
    for leaked in (
        "Smith",
        "Example Street",
        "Rent overdue",
        "@example.org",
    ):
        assert leaked not in body, f"PII-free claim broken: {leaked!r} leaked"


async def test_community_insights_scoped_to_own_org(client, make_user, login):
    async with SessionFactory() as session:
        org_a = await factories.create_organization(session, name="Church A")
        org_b = await factories.create_organization(session, name="Church B")
        await factories.create_assistance_request(session, organization=org_b)
        await session.commit()
        org_b_id = org_b.id
    leader_a = await make_user("faith_leader", organization_id=org_a.id)

    response = client.get(
        f"{API}/dashboard/community-insights", headers=login(leader_a)
    )
    assert response.status_code == 200
    assert response.json()["high_need_categories"] == []

    scoped = client.get(
        f"{API}/dashboard/community-insights?organization_id={org_b_id}",
        headers=login(leader_a),
    )
    assert scoped.status_code == 403


async def test_impact_report_matches_score_service(client, make_user, login):
    from app.services import impact as impact_service

    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        await factories.create_impact_event(session, organization=org, metric="families_supported", value=40)
        await factories.create_impact_event(session, organization=org, metric="meals_provided", value=80)
        await factories.create_impact_rollup(session, organization=org, metric="families_supported", total=40)
        await session.commit()

    response = client.get(f"{API}/dashboard/impact-report", headers=login(leader))
    assert response.status_code == 200, response.text
    body = response.json()

    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        expected = await impact_service.community_impact_score(session, organization_id=org_id)
    assert body["score"] == expected["score"]
    assert body["components"]["families"]["value"] == expected["components"]["families"]
    assert isinstance(body["components"]["families"]["weight"], float)
    assert len(body["months"]) == 1
    assert body["months"][0]["metric"] == "families_supported"
    assert body["months"][0]["total"] == 40


async def test_impact_report_requires_org_for_admin(client, make_user, login):
    admin = await make_user("admin")
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
    response = client.get(f"{API}/dashboard/impact-report", headers=login(admin))
    assert response.status_code == 400

    with_org = client.get(
        f"{API}/dashboard/impact-report?organization_id={org.id}", headers=login(admin)
    )
    assert with_org.status_code == 200


async def test_impact_report_export_csv(client, make_user, login):
    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        await factories.create_impact_config(session, organization=org)
        await factories.create_impact_rollup(session, organization=org, metric="families_supported", total=40)
        await session.commit()

    response = client.get(
        f"{API}/dashboard/impact-report/export?format=csv", headers=login(leader)
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text = response.text
    assert "Community Impact Score" in text
    assert "families_supported" in text
    assert "40" in text


async def test_impact_report_export_pdf(client, make_user, login):
    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        await factories.create_impact_config(session, organization=org)
        await factories.create_impact_rollup(session, organization=org, metric="meals_provided", total=80)
        await session.commit()

    response = client.get(
        f"{API}/dashboard/impact-report/export?format=pdf", headers=login(leader)
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    raw = response.content
    assert raw[:8] == b"%PDF-1.4"
    assert raw.endswith(b"%%EOF\n")
    assert b"/Type /Font" in raw
    assert b"meals_provided" in raw


async def test_insights_and_export_are_auditable(client, make_user, login):
    """Dashboard reads are read-only: nothing may be appended to the audit trail."""
    _, leader = await _org_and_leader(make_user)
    headers = login(leader)
    client.get(f"{API}/dashboard/community-insights", headers=headers)
    client.get(f"{API}/dashboard/impact-report/export?format=csv", headers=headers)

    async with SessionFactory() as session:
        actions = (await session.execute(select(AuditLog.action))).scalars().all()
        assert actions == []