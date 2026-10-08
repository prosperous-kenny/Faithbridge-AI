"""Data access for the ``users`` table.

Routes and dependencies go through this module instead of issuing their own
SELECTs, so identity lookups and the rules around them live in one place.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models import User

# Who may act as a case handler for notifications (PRD §12). Kept as literals:
# importing the Role enum from app.core.rbac would create an import cycle
# (rbac -> deps -> this module), so the enum stays the single source of truth
# for guards while this data-access module names the two roles it queries.
HANDLER_ROLES = ("faith_leader", "admin")


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    """Case-insensitive lookup: emails are stored as typed, matched folded."""
    normalized = email.strip().lower()
    result = await session.execute(
        select(User).where(func.lower(User.email) == normalized)
    )
    return result.scalar_one_or_none()


async def email_exists(session: AsyncSession, email: str) -> bool:
    return await get_by_email(session, email) is not None


async def create(
    session: AsyncSession,
    *,
    email: str,
    full_name: str,
    role: str,
    password: str | None = None,
    organization_id: int | None = None,
    is_active: bool = True,
) -> User:
    """Create a user, hashing the password here so no caller can insert a
    plaintext credential by accident. ``password=None`` leaves the account
    without a local credential (OIDC-provisioned users)."""
    user = User(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        role=role,
        organization_id=organization_id,
        password_hash=hash_password(password) if password is not None else None,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def set_role(session: AsyncSession, user: User, role: str) -> User:
    user.role = role
    await session.flush()
    return user


async def list_handlers(
    session: AsyncSession, *, organization_id: int
) -> list[User]:
    """Active case handlers (faith leaders and admins) of one organization.

    Used to route notifications when a request enters their queue: only users
    who can actually see the case get emailed about it.
    """
    result = await session.execute(
        select(User)
        .where(
            User.organization_id == organization_id,
            User.role.in_(HANDLER_ROLES),
            User.is_active.is_(True),
        )
        .order_by(User.id)
    )
    return list(result.scalars())
