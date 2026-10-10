"""Organization administration (PRD §11 onboarding).

Organizations are the tenancy boundary every other resource hangs off, so
listing and creating them is a platform-administrator concern: a faith leader
is scoped to whatever org an admin assigns and must not be able to invent new
tenants. Creation is audited; there is deliberately no update or delete yet,
because renaming or removing an org de-scopes the users and rows beneath it
and belongs with a dedicated operator runbook.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.session import get_session
from app.repositories import audit as audit_repo
from app.repositories import organizations as organizations_repo
from app.schemas.organizations import OrganizationIn, OrganizationOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Only the system administrator onboards tenants.
ADMIN_ONLY = (Role.ADMIN,)


@router.get(
    "/",
    response_model=list[OrganizationOut],
    dependencies=[Depends(require_role(*ADMIN_ONLY))],
)
async def list_organizations(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[OrganizationOut]:
    """List organizations, oldest first. Bounded and paged so an admin console
    cannot pull an unbounded table into memory."""
    rows = await organizations_repo.list_organizations(
        session, limit=limit, offset=offset
    )
    return [OrganizationOut.model_validate(row) for row in rows]


@router.post(
    "/",
    response_model=OrganizationOut,
    status_code=201,
    dependencies=[Depends(require_role(*ADMIN_ONLY))],
)
async def create_organization(
    payload: OrganizationIn,
    session: SessionDep,
    user: CurrentUser,
) -> OrganizationOut:
    """Create an organization. Faith leaders can then be registered against it
    through ``/auth/register`` with the admin-only ``role`` field."""
    organization = await organizations_repo.create(
        session, name=payload.name, org_type=payload.org_type
    )
    await audit_repo.log_action(
        session,
        action="organization.created",
        entity_type="organization",
        entity_id=str(organization.id),
        organization_id=organization.id,
        actor_id=user.id,
    )
    await session.commit()
    await session.refresh(organization)  # server-side defaults are now on the row
    return OrganizationOut.model_validate(organization)
