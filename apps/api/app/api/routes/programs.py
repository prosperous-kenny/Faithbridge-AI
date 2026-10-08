"""Program directory CRUD (PRD §20).

Faith leaders create and maintain their organization's programs; the donor and
community-member browser sees only active programs across all organizations
(the "public directory" donors match against). A platform admin supersedes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.session import get_session
from app.repositories import audit as audit_repo
from app.repositories import programs as programs_repo
from app.schemas.programs import ProgramIn, ProgramOut, ProgramUpdate

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Program administration is a case-handler concern, not a self-service one:
# anyone can read, only faith leaders (within their org) and admins create.
WRITE_ROLES = (Role.FAITH_LEADER, Role.ADMIN)


@router.get("/", response_model=list[ProgramOut])
async def list_programs(
    session: SessionDep,
    user: CurrentUser,
    active_only: Annotated[Literal["true", "false"] | None, Query()] = None,
) -> list[ProgramOut]:
    """List programs. Faith leaders see their own org (all statuses); members
    and donors browsing the public directory see only active programs; an
    admin without an organization sees everything."""
    if user.role == Role.ADMIN.value:
        rows = await programs_repo.list_programs(
            session, active_only=active_only == "true"
        )
    elif user.role == Role.FAITH_LEADER.value:
        rows = await programs_repo.list_programs(
            session,
            organization_id=user.organization_id,
            active_only=active_only == "true",
        )
    else:
        rows = await programs_repo.list_programs(session, active_only=True)
    return [ProgramOut.model_validate(row) for row in rows]


@router.post(
    "/",
    response_model=ProgramOut,
    status_code=201,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def create_program(
    payload: ProgramIn,
    session: SessionDep,
    user: CurrentUser,
) -> ProgramOut:
    """Create a program. A faith leader may only create one for their own
    organization; dropping a program into a queue its owner cannot see would
    only confuse donation targeting."""
    if user.role == Role.FAITH_LEADER.value:
        if user.organization_id is None:
            raise HTTPException(
                status_code=403,
                detail="A faith leader needs an organization to create programs",
            )
        if payload.organization_id != user.organization_id:
            raise HTTPException(
                status_code=403,
                detail="You can only create programs in your own organization",
            )

    program = await programs_repo.create(
        session,
        organization_id=payload.organization_id,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        location=payload.location,
        budget_needed=payload.budget_needed,
        is_active=payload.is_active,
    )
    await audit_repo.log_action(
        session,
        action="program.created",
        entity_type="program",
        entity_id=str(program.id),
        organization_id=program.organization_id,
        actor_id=user.id,
    )
    await session.commit()
    await session.refresh(program)  # server-side defaults are now on the row
    return ProgramOut.model_validate(program)


@router.patch(
    "/{program_id}",
    response_model=ProgramOut,
    dependencies=[Depends(require_role(*WRITE_ROLES))],
)
async def update_program(
    program_id: int,
    payload: ProgramUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> ProgramOut:
    """Update a program (a partial PATCH). The org guard is the same as
    create; ``exclude_unset`` means a PATCH can deactivate a program without
    resending its other fields."""
    program = await programs_repo.get(session, program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")

    if (
        user.role == Role.FAITH_LEADER.value
        and program.organization_id != user.organization_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage programs in your own organization",
        )

    fields = payload.model_dump(exclude_unset=True)
    if fields:
        await programs_repo.update(session, program, **fields)
    await audit_repo.log_action(
        session,
        action="program.updated",
        entity_type="program",
        entity_id=str(program.id),
        organization_id=program.organization_id,
        actor_id=user.id,
    )
    await session.commit()
    await session.refresh(program)
    return ProgramOut.model_validate(program)