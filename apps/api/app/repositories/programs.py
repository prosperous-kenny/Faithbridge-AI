"""Data access for programs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Program


async def create(
    session: AsyncSession,
    *,
    organization_id: int,
    name: str,
    category: str,
    description: str | None = None,
    location: str | None = None,
    budget_needed: int | None = None,
    is_active: bool = True,
) -> Program:
    program = Program(
        organization_id=organization_id,
        name=name,
        category=category,
        description=description,
        location=location,
        budget_needed=budget_needed,
        is_active=is_active,
    )
    session.add(program)
    await session.flush()
    return program


async def get(session: AsyncSession, program_id: int) -> Program | None:
    """Fetch one program with its organization loaded (needed for matching's
    organization_name and for org-scoped guards)."""
    result = await session.execute(
        select(Program)
        .where(Program.id == program_id)
        .options(selectinload(Program.organization))
    )
    return result.scalar_one_or_none()


async def list_programs(
    session: AsyncSession,
    *,
    organization_id: int | None = None,
    active_only: bool = False,
) -> list[Program]:
    """List programs with their organization loaded.

    ``organization_id`` scopes to one org (own-org lists for faith leaders);
    ``active_only`` restricts to programs still visible to donors. When both
    are unset, every program is returned (all-org views for admins).
    """
    stmt = select(Program).options(selectinload(Program.organization))
    if organization_id is not None:
        stmt = stmt.where(Program.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(Program.is_active.is_(True))
    stmt = stmt.order_by(Program.id)
    result = await session.execute(stmt)
    return list(result.scalars().unique())


async def update(session: AsyncSession, program: Program, **fields: object) -> Program:
    for field, value in fields.items():
        setattr(program, field, value)
    await session.flush()
    return program