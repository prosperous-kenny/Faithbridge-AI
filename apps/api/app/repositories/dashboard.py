"""Aggregate reads for the dashboard endpoints.

Everything in this module returns counts and sums only — never row contents —
so the insight and report surfaces stay PII-free by construction (PRD §22).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AssistanceRequest,
    Beneficiary,
    Donation,
    ImpactEvent,
    Organization,
    Placement,
    Program,
    User,
)
from app.schemas.dashboard import (
    CommunityInsightsOut,
    DonationEffectiveness,
    HighNeedCategory,
    ProgramEffectiveness,
    TrendPoint,
)

# Ordered lookup used by both the query and the response, so adding an entity
# is one edit rather than two that can drift apart.
COUNTED_MODELS: tuple[tuple[str, type], ...] = (
    ("organizations", Organization),
    ("users", User),
    ("programs", Program),
    ("beneficiaries", Beneficiary),
    ("assistance_requests", AssistanceRequest),
    ("donations", Donation),
    ("placements", Placement),
    ("impact_events", ImpactEvent),
)

TERMINAL_REQUEST_STATUSES = ("fulfilled", "declined")


async def entity_counts(session: AsyncSession) -> dict[str, int]:
    """Row counts per entity. Aggregates only: no row contents are read."""
    counts: dict[str, int] = {}
    for key, model in COUNTED_MODELS:
        result = await session.execute(select(func.count()).select_from(model))
        counts[key] = int(result.scalar_one())
    return counts


async def _monthly_donation_totals(
    session: AsyncSession, *, organization_id: int
) -> dict[str, dict[str, int]]:
    """Sum donation amounts per calendar month by lifecycle milestone.

    Returns ``{"YYYY-MM": {"pledged": n, "paid": n, "distributed": n}}``. Each
    milestone is summed against the timestamp column that records when it was
    reached (PRD §8 ledger integrity: a row exists with its timestamps NULL
    until the money actually moves).
    """
    totals: dict[str, dict[str, int]] = {}
    for key, column in (
        ("pledged", Donation.created_at),
        ("paid", Donation.paid_at),
        ("distributed", Donation.distributed_at),
    ):
        month_expr = func.to_char(func.timezone("UTC", column), "YYYY-MM")
        stmt = (
            select(month_expr, func.coalesce(func.sum(Donation.amount), 0))
            .where(
                Donation.organization_id == organization_id,
                column.is_not(None),
            )
            .group_by(month_expr)
        )
        result = await session.execute(stmt)
        for period, amount in result.all():
            totals.setdefault(period, {"pledged": 0, "paid": 0, "distributed": 0})
            totals[period][key] = int(amount)
    return totals


async def community_insights(
    session: AsyncSession, *, organization_id: int
) -> CommunityInsightsOut:
    """Aggregate insights for one organization (PRD Use Case 3).

    Trends, category demand and donation effectiveness are all sums/counts
    grouped from the tables the org owns; no beneficiary row is read, so the
    payload is safe for any viewer that passed the role+scope guard.
    """
    req_month = func.to_char(
        func.timezone("UTC", AssistanceRequest.created_at), "YYYY-MM"
    )
    req_stmt = (
        select(
            req_month,
            func.count(),
            func.coalesce(
                func.sum(case((AssistanceRequest.status == "fulfilled", 1), else_=0)),
                0,
            ),
        )
        .where(AssistanceRequest.organization_id == organization_id)
        .group_by(req_month)
        .order_by(req_month)
    )
    trends: dict[str, dict[str, int]] = {}
    for period, submitted, fulfilled in (await session.execute(req_stmt)).all():
        trends.setdefault(period, {"submitted": 0, "fulfilled": 0})
        trends[period]["submitted"] = int(submitted)
        trends[period]["fulfilled"] = int(fulfilled)

    donation_totals = await _monthly_donation_totals(
        session, organization_id=organization_id
    )
    trend_points = [
        TrendPoint(
            period=period,
            submitted=t["submitted"],
            fulfilled=t["fulfilled"],
            pledged_amount=donation_totals.get(period, {}).get("pledged", 0),
            paid_amount=donation_totals.get(period, {}).get("paid", 0),
            distributed_amount=donation_totals.get(period, {}).get("distributed", 0),
        )
        for period, t in sorted(trends.items())
    ]

    cat_stmt = (
        select(
            AssistanceRequest.category,
            func.coalesce(
                func.sum(
                    case(
                        (AssistanceRequest.status.not_in(TERMINAL_REQUEST_STATUSES), 1),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(case((AssistanceRequest.status == "fulfilled", 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.avg(AssistanceRequest.urgency_score).filter(
                    AssistanceRequest.status.not_in(TERMINAL_REQUEST_STATUSES)
                ),
                0.0,
            ),
        )
        .where(AssistanceRequest.organization_id == organization_id)
        .group_by(AssistanceRequest.category)
        .order_by(AssistanceRequest.category)
    )
    categories = [
        HighNeedCategory(
            category=category,
            open=int(open_count),
            fulfilled=int(fulfilled),
            avg_urgency=round(float(avg_urgency), 1),
        )
        for category, open_count, fulfilled, avg_urgency in (
            await session.execute(cat_stmt)
        ).all()
    ]

    totals_stmt = select(
        func.coalesce(func.sum(Donation.amount).filter(Donation.paid_at.is_not(None)), 0),
        func.coalesce(
            func.sum(Donation.amount).filter(Donation.allocated_at.is_not(None)), 0
        ),
        func.coalesce(
            func.sum(Donation.amount).filter(Donation.distributed_at.is_not(None)), 0
        ),
    ).where(Donation.organization_id == organization_id)
    paid, allocated, distributed = (await session.execute(totals_stmt)).one()

    program_stmt = (
        select(
            Program.id,
            Program.name,
            func.coalesce(
                func.sum(Donation.amount).filter(Donation.status == "pledged"), 0
            ),
            func.coalesce(
                func.sum(
                    Donation.amount
                ).filter(Donation.distributed_at.is_not(None)),
                0,
            ),
        )
        .join(Donation, Donation.program_id == Program.id)
        .where(Program.organization_id == organization_id)
        .group_by(Program.id, Program.name)
        .order_by(Program.name)
    )
    per_program = [
        ProgramEffectiveness(
            program_id=program_id, name=name, pledged_amount=int(pledged), distributed_amount=int(distributed)
        )
        for program_id, name, pledged, distributed in (await session.execute(program_stmt)).all()
    ]

    total_pledged = sum(p.pledged_amount for p in per_program)

    return CommunityInsightsOut(
        organization_id=organization_id,
        trends=trend_points,
        high_need_categories=categories,
        donation_effectiveness=DonationEffectiveness(
            pledged_amount=total_pledged,
            paid_amount=int(paid),
            allocated_amount=int(allocated),
            distributed_amount=int(distributed),
            per_program=per_program,
        ),
    )


async def impact_report_months(
    session: AsyncSession,
    *,
    organization_id: int,
) -> list[tuple[tuple[datetime, datetime, str], int]]:
    """The materialised rollup rows for a report, oldest period last (lean
    server-side so the export and the JSON view share the same shape)."""
    from app.repositories import impact as impact_repo

    rows = await impact_repo.list_rollups(
        session, organization_id=organization_id, limit=500
    )
    return [((r.period_start, r.period_end, r.metric), r.total) for r in rows]
