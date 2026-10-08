from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.session import get_session
from app.repositories import placements as placements_repo
from app.schemas.placements import (
    PlacementIn,
    PlacementMatchIn,
    PlacementMatchOut,
    PlacementOut,
    PlacementStatusUpdateIn,
)
from app.services import employment

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LeaderRoles = (Role.FAITH_LEADER, Role.ADMIN)


@router.post(
    "/placements",
    response_model=PlacementOut,
    status_code=201,
    dependencies=[Depends(require_role(*LeaderRoles))],
)
async def create_placement(
    payload: PlacementIn,
    session: SessionDep,
    user: CurrentUser,
) -> PlacementOut:
    beneficiary = await placements_repo.get_beneficiary(session, payload.beneficiary_id)
    if beneficiary is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    if user.organization_id is not None and beneficiary.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Only your own organization")
    placement = await placements_repo.create_placement(
        session,
        beneficiary=beneficiary,
        employer=payload.employer,
        role_title=payload.role_title,
        skills=payload.skills,
        mentor_user_id=payload.mentor_user_id,
    )
    await session.commit()
    await session.refresh(placement)
    return PlacementOut.model_validate(placement)


@router.get("/placements", response_model=list[PlacementOut])
async def list_placements(
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PlacementOut]:
    org_id = user.organization_id
    is_admin = user.role == Role.ADMIN.value
    rows = await placements_repo.list_placements(
        session, organization_id=None if is_admin else org_id, limit=limit, offset=offset
    )
    return [PlacementOut.model_validate(r) for r in rows]


@router.patch(
    "/placements/{placement_id}/status",
    response_model=PlacementOut,
    dependencies=[Depends(require_role(*LeaderRoles))],
)
async def update_placement_status(
    placement_id: int,
    payload: PlacementStatusUpdateIn,
    session: SessionDep,
    user: CurrentUser,
) -> PlacementOut:
    placement = await placements_repo.list_placements(
        session, organization_id=user.organization_id, limit=500, offset=0
    )
    # filter
    found = next((p for p in placement if p.id == placement_id), None)
    if found is None and user.role == Role.ADMIN.value:
        found = next((p for p in await placements_repo.list_placements(session, limit=500) if p.id == placement_id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="Placement not found")
    updated = await placements_repo.update_placement_status(session, placement_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="Placement not found")
    await session.commit()
    await session.refresh(updated)
    return PlacementOut.model_validate(updated)


@router.post(
    "/placements/match",
    response_model=PlacementMatchOut,
    dependencies=[Depends(require_role(*LeaderRoles))],
)
async def match_placements(
    payload: PlacementMatchIn,
    session: SessionDep,
    user: CurrentUser,
) -> PlacementMatchOut:
    beneficiary = await placements_repo.get_beneficiary(session, payload.beneficiary_id)
    if beneficiary is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    if user.organization_id is not None and beneficiary.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Only your own organization")
    matches = await employment.match_jobs(
        session,
        organization_id=beneficiary.organization_id,
        skills=beneficiary.skills if hasattr(beneficiary, "skills") else [],
        limit=payload.limit,
    )
    return PlacementMatchOut(
        beneficiary_id=beneficiary.id,
        skills=getattr(beneficiary, "skills", []),
        matches=matches,
    )