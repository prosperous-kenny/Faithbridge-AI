"""Role definitions and the ``require_role`` route guard (PRD §12)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.db.models import User
from app.db.session import get_session


class Role(str, Enum):
    """The four roles in PRD §12, spelled exactly as PRD §20 stores them."""

    COMMUNITY_MEMBER = "community_member"
    DONOR = "donor"
    FAITH_LEADER = "faith_leader"
    ADMIN = "admin"

    def __str__(self) -> str:  # pragma: no cover - repr convenience
        return self.value


ROLE_VALUES: frozenset[str] = frozenset(role.value for role in Role)

# Roles a caller may choose at self-service registration. Faith leaders are
# created by an existing admin after an organisation is onboarded, and admin
# must never be self-grantable: otherwise the first account anyone registers
# controls the platform (PRD §11 "Secure Authentication").
SELF_REGISTERABLE_ROLES: frozenset[Role] = frozenset(
    {Role.COMMUNITY_MEMBER, Role.DONOR}
)


def role_permits(user_role: str, allowed: frozenset[Role]) -> bool:
    """Fail-closed role check.

    The system administrator supersedes every other role: PRD §12 names it
    "System Administrator", and an operator who cannot reach a screen cannot
    operate it. Any role value that is not one of the four known roles is
    denied outright rather than treated as a match for something.
    """
    try:
        role = Role(user_role)
    except ValueError:
        return False
    if role in allowed:
        return True
    return role is Role.ADMIN


def require_role(*allowed: Role) -> Callable[..., Awaitable[User]]:
    """Route guard: reject anonymous callers with 401 and the wrong role with 403.

    Usage::

        @router.get("/items", dependencies=[Depends(require_role(Role.DONOR))])

    Returns the authenticated user so a route can also declare
    ``Depends(require_role(...))`` in its signature and receive it directly.
    """
    if not allowed:
        raise ValueError("require_role() needs at least one role")
    allowed_set = frozenset(allowed)

    async def guard(current: CurrentUser) -> User:
        if not role_permits(current.role, allowed_set):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        return current

    return guard


async def get_optional_admin(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    """Return the caller if they are an authenticated admin, else None.

    Never raises: used where an endpoint is open to everyone but accepts extra
    authority from an administrator (creating faith-leader accounts), so an
    anonymous caller must not produce a 401 on a route that is otherwise open.
    """
    try:
        user = await get_current_user(request, session)
    except HTTPException:
        return None
    try:
        return user if Role(user.role) is Role.ADMIN else None
    except ValueError:
        # Unknown role in the database: not an admin, but also not a crash.
        return None
