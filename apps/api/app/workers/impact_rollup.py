"""Impact rollup aggregation job (Phase 4).

Aggregates the append-only ``impact_events`` feed into per-organisation period
totals stored in ``impact_rollups``. Like Phase 2's workers this is executed
in-process via FastAPI ``BackgroundTasks`` when no broker is configured, and
the same function is the body of a Celery task when ``CELERY_BROKER_URL`` is
set: ``app/workers/celery_app.py`` routes ``app.workers.tasks.*`` to the
``assistance`` queue, and this module can be registered identically.

A rollup is a *replacement*, not an append: for each organization it deletes
the rows for the period and materialises fresh totals, so re-running is
idempotent and dashboards never double-count a drifted aggregation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ImpactEvent
from app.db.session import SessionFactory
from app.repositories import impact as impact_repo

PERIODS = ("daily", "monthly")


def period_bounds(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Half-open ``[start, end)`` bounds for a daily or monthly period.

    Returns naive UTC datetimes to match the TIMESTAMP WITHOUT TIME ZONE
    columns they will be compared against.
    """
    if period not in PERIODS:
        raise ValueError(f"Unknown rollup period {period!r}; expected one of {PERIODS}")
    anchor = now or datetime.now(UTC)
    anchor = anchor.replace(tzinfo=None)
    if period == "daily":
        start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        start = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    return start, end


async def rollup_organization(
    session: AsyncSession,
    *,
    organization_id: int,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    """Recompute one organization's totals for ``[start, end)``."""
    return await impact_repo.replace_period_totals(
        session,
        organization_id=organization_id,
        period_start=start,
        period_end=end,
    )


async def impact_rollup(
    period: str = "monthly", *, organization_id: int | None = None
) -> dict:
    """Run the aggregation for every organization (or one), returning a map of
    per-organization metric totals so callers can audit what landed."""
    start, end = period_bounds(period)
    async with SessionFactory() as session:
        org_stmt = select(ImpactEvent.organization_id).distinct()
        if organization_id is not None:
            org_stmt = org_stmt.where(ImpactEvent.organization_id == organization_id)
        result = await session.execute(org_stmt)
        org_ids = [row[0] for row in result.all()]
        totals: dict[int, dict[str, int]] = {}
        for org_id in org_ids:
            totals[org_id] = await rollup_organization(
                session, organization_id=org_id, start=start, end=end
            )
        await session.commit()
    return {
        "period": period,
        "period_start": start,
        "period_end": end,
        "organizations": len(org_ids),
        "totals": totals,
    }