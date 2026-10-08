"""Impact feed, Community Impact Score, config and rollups (Phase 4).

The impact surface is handler-facing (faith leader of the owning org, or the
platform admin): it records outcomes for an organization, reads the score and
its component breakdown, and runs/reads the period rollups that feed
dashboards and the M1 report. Donor-facing insight endpoints (PII-free, PRD
Use Case 3) are Phase 5's ``/dashboard`` work and stay separate routes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.session import get_session
from app.repositories import impact as impact_repo
from app.schemas.impact import (
    ImpactComponent,
    ImpactConfigIn,
    ImpactConfigOut,
    ImpactEventIn,
    ImpactEventListOut,
    ImpactEventOut,
    ImpactScoreOut,
    RollupListOut,
    RollupOut,
    RollupRunOut,
)
from app.services import impact as impact_service
from app.services.audit import record as audit_record
from app.workers.impact_rollup import PERIODS, impact_rollup

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

HANDLER_ROLES = (Role.FAITH_LEADER, Role.ADMIN)


def _resolve_read_org(user, requested: int | None) -> int | None:
    """The organization a read applies to. Leaders are locked to their own;
    admins choose any (or None to span all). None means "all" for admin
    reads and is never returned for a leader."""
    if user.organization_id is not None:
        if requested is not None and requested != user.organization_id:
            raise HTTPException(
                status_code=403,
                detail="You can only access your own organization's impact data",
            )
        return user.organization_id
    return requested


def _resolve_write_org(user, requested: int | None) -> int:
    """The organization a domain action writes to. Leaders must write to their
    own org; an admin must say which org they are recording for."""
    if user.organization_id is not None:
        if requested is not None and requested != user.organization_id:
            raise HTTPException(
                status_code=403,
                detail="You can only record impact for your own organization",
            )
        return user.organization_id
    if requested is None:
        raise HTTPException(
            status_code=400,
            detail="organization_id is required for a platform admin write",
        )
    return requested


@router.post(
    "/events",
    response_model=ImpactEventOut,
    status_code=201,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def create_event(
    payload: ImpactEventIn,
    session: SessionDep,
    user: CurrentUser,
) -> ImpactEventOut:
    """Record one outcome for the organization (e.g. meals provided, medical
    cases supported). Recording is the domain action; the feed itself stays
    append-only — there is no update or delete surface."""
    organization_id = _resolve_write_org(user, payload.organization_id)
    event = await impact_service.record_event(
        session,
        organization_id=organization_id,
        metric=payload.metric,
        value=payload.value,
        occurred_at=payload.occurred_at,
    )
    await audit_record(
        session,
        action="impact.event.recorded",
        entity_type="impact_event",
        entity_id=str(event.id),
        organization_id=organization_id,
        actor_id=user.id,
        note=f"{payload.metric} = {payload.value}",
    )
    await session.commit()
    await session.refresh(event)
    return ImpactEventOut.model_validate(event)


@router.get(
    "/events",
    response_model=ImpactEventListOut,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def list_events(
    session: SessionDep,
    user: CurrentUser,
    organization_id: Annotated[int | None, Query()] = None,
    metric: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImpactEventListOut:
    org = _resolve_read_org(user, organization_id)
    rows = await impact_repo.list_events(
        session, organization_id=org, metric=metric, limit=limit, offset=offset
    )
    return ImpactEventListOut(
        items=[ImpactEventOut.model_validate(row) for row in rows], count=len(rows)
    )


@router.get(
    "/score",
    response_model=ImpactScoreOut,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def get_score(
    session: SessionDep,
    user: CurrentUser,
    organization_id: Annotated[int | None, Query()] = None,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> ImpactScoreOut:
    """The 0-100 Community Impact Score (PRD §15) with its per-dimension
    breakdown, so a report can show not just the number but why."""
    org = _resolve_read_org(user, organization_id)
    if org is None:
        raise HTTPException(status_code=400, detail="organization_id is required")
    result = await impact_service.community_impact_score(session, organization_id=org)
    return ImpactScoreOut(
        organization_id=org,
        score=result["score"],
        components={
            dimension: ImpactComponent(
                value=result["components"][dimension],
                weight=result["weights"][dimension],
                target=result["targets"][dimension],
            )
            for dimension in impact_service.DIMENSIONS
        },
    )


@router.put(
    "/config",
    response_model=ImpactConfigOut,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def update_config(
    payload: ImpactConfigIn,
    session: SessionDep,
    user: CurrentUser,
) -> ImpactConfigOut:
    """Per-organization Impact Score weights and targets (PRD §15 "weights
    configurable per organization"). Any write is audited because it changes a
    public measurement."""
    org = _resolve_write_org(user, None)
    weights = payload.weights or {}
    targets = payload.targets or {}
    for dimension in weights:
        if dimension not in impact_service.DIMENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown dimension {dimension!r}; expected "
                + ", ".join(impact_service.DIMENSIONS),
            )
    if weights:
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-6:
            raise HTTPException(status_code=422, detail="Weights must sum to 1.0")
    for dimension in targets:
        if dimension not in impact_service.DIMENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown dimension {dimension!r}; expected "
                + ", ".join(impact_service.DIMENSIONS),
            )
        if targets[dimension] <= 0:
            raise HTTPException(status_code=422, detail="Targets must be positive")
    config = await impact_repo.upsert_config(
        session, organization_id=org, weights=weights, targets=targets
    )
    await audit_record(
        session,
        action="impact.config.updated",
        entity_type="org_impact_config",
        entity_id=str(org),
        organization_id=org,
        actor_id=user.id,
        note=f"weights={weights} targets={targets}",
    )
    await session.commit()
    await session.refresh(config)
    return ImpactConfigOut.model_validate(config)


@router.get(
    "/config",
    response_model=ImpactConfigOut | None,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def get_config(
    session: SessionDep,
    user: CurrentUser,
    organization_id: Annotated[int | None, Query()] = None,
) -> ImpactConfigOut | None:
    """The active config, or the PRD baseline when none has been recorded."""
    org = _resolve_read_org(user, organization_id)
    if org is None:
        raise HTTPException(status_code=400, detail="organization_id is required")
    config = await impact_repo.get_config(session, org)
    if config is None:
        weights = impact_service.DEFAULT_WEIGHTS
        targets = impact_service.DEFAULT_TARGETS
        return ImpactConfigOut(
            organization_id=org,
            families_weight=weights["families"],
            education_weight=weights["education"],
            employment_weight=weights["employment"],
            food_security_weight=weights["food_security"],
            healthcare_weight=weights["healthcare"],
            families_target=targets["families"],
            education_target=targets["education"],
            employment_target=targets["employment"],
            food_security_target=targets["food_security"],
            healthcare_target=targets["healthcare"],
        )
    return ImpactConfigOut.model_validate(config)


@router.get(
    "/rollups",
    response_model=RollupListOut,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def list_rollups(
    session: SessionDep,
    user: CurrentUser,
    organization_id: Annotated[int | None, Query()] = None,
    metric: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RollupListOut:
    org = _resolve_read_org(user, organization_id)
    rows = await impact_repo.list_rollups(
        session, organization_id=org, metric=metric, limit=limit, offset=offset
    )
    return RollupListOut(items=[RollupOut.model_validate(row) for row in rows], count=len(rows))


@router.post(
    "/rollups/run",
    response_model=RollupRunOut,
    status_code=201,
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def run_rollup(
    period: Annotated[str, Query()] = "monthly",
) -> RollupRunOut:
    """Run the aggregation job for the current period. Executed in-process
    when no broker is configured (the Celery adapter exposes the same
    function); idempotent by construction."""
    if period not in PERIODS:
        raise HTTPException(status_code=422, detail=f"period must be one of {PERIODS}")
    result = await impact_rollup(period)
    return RollupRunOut(**result)