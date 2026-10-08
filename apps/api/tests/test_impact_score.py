"""Phase 4 impact feed: append-only events, the Community Impact Score (PRD
§8, §15), per-organization configurable weights, and period rollups that
reconcile exactly with the donation ledger.

The gate part of this file is the reconciliation: for a seeded period, the
``donations_distributed`` rollup total must equal the sum of distributed
donation amounts — the impact ledger agrees with the money ledger.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import Donation, ImpactRollup
from app.db.session import SessionFactory
from app.repositories import impact as impact_repo
from app.services import impact as impact_service
from app.workers.impact_rollup import impact_rollup
from tests import factories

API = "/api/v1"

DIMENSIONS_ORDER = (
    "families",
    "education",
    "employment",
    "food_security",
    "healthcare",
)


async def _org_and_leader(make_user):
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        org_id = org.id
    leader = await make_user("faith_leader", organization_id=org_id)
    return org_id, leader


async def test_unknown_metric_is_rejected():
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.flush()
        try:
            await impact_service.record_event(
                session, organization_id=org.id, metric="made_up", value=1
            )
            assert False, "expected ValueError for unknown metric"
        except ValueError as exc:
            assert "Unknown impact metric" in str(exc)


async def test_events_are_append_only_writer():
    """The repository exposes no update or delete surface — the module must
    not even define one."""
    import inspect

    source = inspect.getsource(impact_repo)
    assert "def update_event" not in source
    assert "def delete_event" not in source


async def test_score_matches_hand_computed_value(client, make_user, login):
    org_id, leader = await _org_and_leader(make_user)
    async with SessionFactory() as session:
        org = await session.get(factories.Organization, org_id)
        await factories.create_impact_event(
            session, organization=org, metric="families_supported", value=80
        )
        await factories.create_impact_event(
            session, organization=org, metric="meals_provided", value=50
        )
        # Configure targets so the maths is round: families 100 -> 80, food 200 -> 25.
        await factories.create_impact_config(
            session,
            organization=org,
            weights={"families": 0.5, "food_security": 0.5, "education": 0.0, "employment": 0.0, "healthcare": 0.0},
            targets={"families": 100.0, "food_security": 200.0},
        )
        await session.commit()

    response = client.get(f"{API}/impact/score", headers=login(leader))
    assert response.status_code == 200, response.text
    body = response.json()
    # families component = min(100, 100*80/100) = 80; food = min(100, 100*50/200)=25
    # score = 0.5*80 + 0.5*25 = 52.5 -> round = 52 (half to even) or 53
    assert body["score"] in (52, 53)
    assert body["components"]["families"]["value"] == 80
    assert body["components"]["food_security"]["value"] == 25


async def test_weights_differ_per_organization(client, make_user, login):
    """Same underlying events, different config -> different scores."""
    async with SessionFactory() as session:
        org_a = await factories.create_organization(session)
        org_b = await factories.create_organization(session)
        await factories.create_impact_event(
            session, organization=org_a, metric="families_supported", value=100
        )
        await factories.create_impact_event(
            session, organization=org_b, metric="families_supported", value=100
        )
        await factories.create_impact_config(
            session,
            organization=org_a,
            weights={"families": 1.0, "education": 0.0, "employment": 0.0, "food_security": 0.0, "healthcare": 0.0},
        )
        await factories.create_impact_config(
            session,
            organization=org_b,
            weights={"education": 1.0, "families": 0.0, "employment": 0.0, "food_security": 0.0, "healthcare": 0.0},
        )
        await session.commit()
        org_a_id, org_b_id = org_a.id, org_b.id

    async with SessionFactory() as session:
        score_a = await impact_service.community_impact_score(session, organization_id=org_a_id)
        score_b = await impact_service.community_impact_score(session, organization_id=org_b_id)
    # org A values families at 100 -> score 100; org B ignores it -> 0.
    assert score_a["score"] == 100
    assert score_b["score"] == 0


async def test_score_reproducible_from_config_alone(client):
    """Recording events and then recomputing by hand with the stored config
    must reproduce the service's answer (the gate's "from config alone")."""
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await factories.create_impact_event(
            session, organization=org, metric="families_supported", value=40
        )
        await factories.create_impact_event(
            session, organization=org, metric="employment_placements", value=10
        )
        await factories.create_impact_config(
            session,
            organization=org,
            weights={"families": 0.5, "employment": 0.5, "education": 0.0, "food_security": 0.0, "healthcare": 0.0},
            targets={"families": 80.0, "employment": 40.0},
        )
        await session.commit()
        org_id = org.id

    async with SessionFactory() as session:
        result = await impact_service.community_impact_score(session, organization_id=org_id)
        config = await impact_repo.get_config(session, org_id)

    # Hand computation from the stored config alone.
    families = min(100, round(100 * 40 / config.families_target))
    employment = min(100, round(100 * 10 / config.employment_target))
    expected = round(
        config.families_weight * families + config.employment_weight * employment
    )
    assert result["score"] == expected
    assert families == 50 and employment == 25
    assert expected in (37, 38)


async def test_rollup_reconciles_with_donation_ledger(client, make_user, login):
    """Impact totals reconcile exactly with the donation ledger: the
    donations_distributed rollup equals the sum of distributed donations."""
    donor = await make_user("donor")
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        _, beneficiary, _ = await factories.create_assistance_request(
            session, organization=org
        )
        await session.commit()
        org_id = org.id
        beneficiary_id = beneficiary.id
    leader = await make_user("faith_leader", organization_id=org_id)
    leader_headers = login(leader)
    donor_headers = login(donor)

    amounts = (5000, 7000, 4000)
    for amount in amounts:
        pledge = client.post(
            f"{API}/donations/",
            headers=donor_headers,
            json={"organization_id": org_id, "amount": amount},
        )
        assert pledge.status_code == 201
        donation_id = pledge.json()["id"]
        for status in ("paid", "allocated", "distributed"):
            payload = {"status": status}
            if status == "allocated":
                payload["beneficiary_id"] = beneficiary_id
            response = client.patch(
                f"{API}/donations/{donation_id}/status",
                headers=leader_headers,
                json=payload,
            )
            assert response.status_code == 200, response.text

    result = await impact_rollup("monthly")
    assert org_id in result["totals"]

    async with SessionFactory() as session:
        rollup_total = (
            await session.execute(
                select(func.coalesce(func.sum(ImpactRollup.total), 0)).where(
                    ImpactRollup.metric == "donations_distributed",
                    ImpactRollup.organization_id == org_id,
                )
            )
        ).scalar_one()
        ledger_total = (
            await session.execute(
                select(func.coalesce(func.sum(Donation.amount), 0)).where(
                    Donation.status == "distributed",
                    Donation.organization_id == org_id,
                )
            )
        ).scalar_one()
    assert rollup_total == ledger_total == sum(amounts)