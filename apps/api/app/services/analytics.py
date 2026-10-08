"""Advanced analytics: aggregates over the ledger and case feed (PRD §14).

Everything is an integer or a mean over derived rows, so the responses are
PII-free by construction the same way the Phase 5 dashboard aggregates are.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Donation, Program


async def donor_retention(
    session: AsyncSession,
    *,
    organization_id: int,
    months: int = 6,
) -> dict:
    """Donors who donated again in a later month, by month.

    A donor is "retained" in month N if they have a paid-or-beyond donation in
    months N-1 and N. Returns per-month counts and the platform-wide simple
    retention rate across the window.
    """
    stmt = (
        select(
            func.to_char(func.timezone("UTC", Donation.created_at), "YYYY-MM").label("month"),
            Donation.donor_id,
        )
        .where(
            Donation.organization_id == organization_id,
            Donation.status.in_(("paid", "allocated", "distributed")),
        )
        .distinct()
    )
    rows = list((await session.execute(stmt)).all())

    monthly: dict[str, set[int]] = {}
    for month, donor_id in rows:
        monthly.setdefault(month, set()).add(donor_id)

    ordered = sorted(monthly)[-months:]
    buckets: list[dict[str, object]] = []
    for month in ordered:
        months_idx = ordered.index(month)
        repeat = 0
        if months_idx > 0 and month in monthly:
            previous = ordered[months_idx - 1]
            repeat = len(monthly[month] & monthly[previous])
        buckets.append({"period": month, "active_donors": len(monthly[month]), "retained": repeat})

    eligible = [b for b in buckets if b["period"] in monthly and b["period"] != ordered[0]]
    rate = round(sum(b["retained"] for b in eligible) / max(1, sum(b["active_donors"] for b in eligible)), 3)
    return {"buckets": buckets, "retention_rate": rate}


async def distribution_efficiency(
    session: AsyncSession,
    *,
    organization_id: int,
) -> dict:
    """Mean days between payment and distribution for completed donations."""
    result = await session.execute(
        select(
            func.avg(
                func.date_part("epoch", Donation.distributed_at - Donation.paid_at) / 86400
            )
        ).where(
            Donation.status == "distributed",
            Donation.organization_id == organization_id,
            Donation.paid_at.isnot(None),
            Donation.distributed_at.isnot(None),
        )
    )
    mean_days = result.scalar_one()
    return {
        "organization_id": organization_id,
        "mean_days_paid_to_distributed": round(mean_days, 2) if mean_days is not None else None,
        "distributed_count": (
            await session.execute(
                select(func.count()).select_from(Donation).where(
                    Donation.status == "distributed",
                    Donation.organization_id == organization_id,
                )
            )
        ).scalar_one(),
    }


async def program_effectiveness(
    session: AsyncSession,
    *,
    organization_id: int,
) -> list[dict]:
    """Per program: distributed vs pledged, as a utilisation ratio."""
    stmt = (
        select(
            Program.id,
            Program.name,
            func.coalesce(func.sum(Donation.amount).filter(Donation.status.in_(("paid", "allocated", "distributed"))), 0),
            func.coalesce(func.sum(Donation.amount).filter(Donation.status == "distributed"), 0),
        )
        .join(Donation, Donation.program_id == Program.id)
        .where(Program.organization_id == organization_id)
        .group_by(Program.id, Program.name)
        .order_by(Program.name)
    )
    result = await session.execute(stmt)
    return [
        {
            "program_id": program_id,
            "name": name,
            "raised_amount": raised,
            "distributed_amount": distributed,
            "distribution_ratio": round(distributed / raised, 3) if raised else 0.0,
        }
        for program_id, name, raised, distributed in result
    ]