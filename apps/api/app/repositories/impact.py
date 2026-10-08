"""Impact event repository: append-only feed, config, and rollups (Phase 4).

``impact_events`` is append-only by construction: there is no update or delete
helper here, and the route surface for recording events is a service-domain
action (record an outcome) that also writes an audit row. The only mechanism
that rewrites impact data is the rollup materialisation, and it writes to the
separate, replaceable ``impact_rollups`` table — never through this module.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ImpactEvent, ImpactRollup, OrgImpactConfig


async def create_event(
    session: AsyncSession,
    *,
    organization_id: int,
    metric: str,
    value: int,
    occurred_at: datetime | None = None,
) -> ImpactEvent:
    event = ImpactEvent(
        organization_id=organization_id,
        metric=metric,
        value=value,
        occurred_at=occurred_at or func.now(),
    )
    session.add(event)
    await session.flush()
    return event


async def list_events(
    session: AsyncSession,
    *,
    organization_id: int | None = None,
    metric: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[ImpactEvent]:
    stmt = select(ImpactEvent).order_by(ImpactEvent.occurred_at.desc(), ImpactEvent.id.desc())
    if organization_id is not None:
        stmt = stmt.where(ImpactEvent.organization_id == organization_id)
    if metric is not None:
        stmt = stmt.where(ImpactEvent.metric == metric)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars())


async def events_in_period(
    session: AsyncSession,
    *,
    organization_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[ImpactEvent]:
    stmt = select(ImpactEvent).where(ImpactEvent.organization_id == organization_id)
    if start is not None:
        stmt = stmt.where(ImpactEvent.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(ImpactEvent.occurred_at < end)
    result = await session.execute(stmt)
    return list(result.scalars())


async def get_config(session: AsyncSession, organization_id: int) -> OrgImpactConfig | None:
    stmt = select(OrgImpactConfig).where(
        OrgImpactConfig.organization_id == organization_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_config(
    session: AsyncSession,
    *,
    organization_id: int,
    weights: dict[str, float] | None = None,
    targets: dict[str, float] | None = None,
) -> OrgImpactConfig:
    config = await get_config(session, organization_id)
    if config is None:
        config = OrgImpactConfig(organization_id=organization_id)
        session.add(config)
    from app.services.impact import DIMENSIONS

    mapping = {
        "families": ("families_weight", "families_target"),
        "education": ("education_weight", "education_target"),
        "employment": ("employment_weight", "employment_target"),
        "food_security": ("food_security_weight", "food_security_target"),
        "healthcare": ("healthcare_weight", "healthcare_target"),
    }
    for dimension in DIMENSIONS:
        weight_col, target_col = mapping[dimension]
        if weights is not None and dimension in weights:
            setattr(config, weight_col, weights[dimension])
        if targets is not None and dimension in targets:
            setattr(config, target_col, targets[dimension])
    await session.flush()
    return config


async def list_rollups(
    session: AsyncSession,
    *,
    organization_id: int | None = None,
    metric: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[ImpactRollup]:
    stmt = select(ImpactRollup).order_by(
        ImpactRollup.period_end.desc(), ImpactRollup.metric
    )
    if organization_id is not None:
        stmt = stmt.where(ImpactRollup.organization_id == organization_id)
    if metric is not None:
        stmt = stmt.where(ImpactRollup.metric == metric)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars())


async def replace_period_totals(
    session: AsyncSession,
    *,
    organization_id: int,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, int]:
    """Recompute one organization's totals for a half-open ``[start, end)``
    period from the append-only feed, replacing any existing rows.

    Returns the metric -> total map so callers can audit what landed.
    """
    await session.execute(
        delete(ImpactRollup).where(
            ImpactRollup.organization_id == organization_id,
            ImpactRollup.period_start == period_start,
            ImpactRollup.period_end == period_end,
        )
    )
    events = await events_in_period(
        session, organization_id=organization_id, start=period_start, end=period_end
    )
    totals: dict[str, int] = {}
    for event in events:
        totals[event.metric] = totals.get(event.metric, 0) + event.value
    for metric, total in sorted(totals.items()):
        session.add(
            ImpactRollup(
                organization_id=organization_id,
                period_start=period_start,
                period_end=period_end,
                metric=metric,
                total=total,
            )
        )
    await session.flush()
    return totals