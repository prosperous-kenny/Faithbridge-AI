"""Volunteer registration and matching (PRD §14, Phase 3).

Any authenticated member may hold a volunteer profile (donors and community
members alike — PRD §5 volunteers are their own audience), so registration is
a self-service upsert: re-submitting updates the same row instead of failing
on the unique ``user_id`` constraint. Ranking and the directory are handler
work (faith leader / admin), scoped to the caller's organization.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.models import Volunteer
from app.db.session import get_session
from app.repositories import audit as audit_repo
from app.schemas.volunteers import (
    VolunteerIn,
    VolunteerMatchIn,
    VolunteerMatchOut,
    VolunteerOut,
)
from app.services.volunteering import match_volunteers

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
LeaderRoles = (Role.FAITH_LEADER, Role.ADMIN)
# PRD §20 gives each user one role, but volunteering is open to all four.
AllRoles = (
    Role.COMMUNITY_MEMBER,
    Role.DONOR,
    Role.FAITH_LEADER,
    Role.ADMIN,
)


def _resolve_organization(payload_org: int | None, user: CurrentUser) -> int:
    """The organization this action applies to, with the usual org-scope rule.

    Bound users act only within their own organization; a platform admin
    without an organization must say which one they mean.
    """
    organization_id = (
        payload_org if payload_org is not None else user.organization_id
    )
    if organization_id is None:
        raise HTTPException(
            status_code=422,
            detail="organization_id is required for users without an organization",
        )
    if user.organization_id is not None and organization_id != user.organization_id:
        raise HTTPException(
            status_code=403,
            detail="You can only act within your own organization",
        )
    return organization_id


@router.post(
    "",
    response_model=VolunteerOut,
    status_code=201,
    dependencies=[Depends(require_role(*AllRoles))],
)
async def save_volunteer_profile(
    payload: VolunteerIn,
    session: SessionDep,
    user: CurrentUser,
) -> VolunteerOut:
    """Create or update the caller's volunteer profile (upsert)."""
    organization_id = _resolve_organization(payload.organization_id, user)

    existing = (
        await session.execute(select(Volunteer).where(Volunteer.user_id == user.id))
    ).scalar_one_or_none()

    if existing is None:
        volunteer = Volunteer(
            user_id=user.id,
            organization_id=organization_id,
            skills=payload.skills,
            availability=payload.availability,
        )
        session.add(volunteer)
        action = "volunteer.profile.created"
    else:
        volunteer = existing
        volunteer.organization_id = organization_id
        volunteer.skills = payload.skills
        volunteer.availability = payload.availability
        volunteer.is_active = True
        action = "volunteer.profile.updated"

    await session.flush()
    await audit_repo.log_action(
        session,
        action=action,
        entity_type="volunteer",
        entity_id=str(volunteer.id),
        organization_id=organization_id,
        actor_id=user.id,
    )
    await session.commit()
    await session.refresh(volunteer)
    return VolunteerOut.model_validate(volunteer)


@router.get(
    "",
    response_model=list[VolunteerOut],
    dependencies=[Depends(require_role(*LeaderRoles))],
)
async def list_volunteers(
    session: SessionDep,
    user: CurrentUser,
    only_active: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[VolunteerOut]:
    """The organization's volunteer directory (handler roles only)."""
    stmt = select(Volunteer).options(selectinload(Volunteer.user))
    if user.organization_id is not None:
        stmt = stmt.where(Volunteer.organization_id == user.organization_id)
    if only_active:
        stmt = stmt.where(Volunteer.is_active.is_(True))
    stmt = stmt.order_by(Volunteer.id).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars()
    return [VolunteerOut.model_validate(row) for row in rows]


@router.post(
    "/match",
    response_model=VolunteerMatchOut,
    dependencies=[Depends(require_role(*LeaderRoles))],
)
async def match(
    payload: VolunteerMatchIn,
    session: SessionDep,
    user: CurrentUser,
) -> VolunteerMatchOut:
    """Rank this organization's active volunteers against a need.

    Returns name and user id only — no email, phone, or address (PRD §22
    data minimization; the directory's consumers are handlers, but the
    response carries nothing a match explanation would not need).
    """
    organization_id = _resolve_organization(payload.organization_id, user)
    matches = await match_volunteers(
        session,
        organization_id=organization_id,
        skills=payload.skills,
        availability=payload.availability,
        limit=payload.limit,
    )
    return VolunteerMatchOut(
        organization_id=organization_id,
        skills=payload.skills,
        availability=payload.availability,
        matches=matches,
    )
