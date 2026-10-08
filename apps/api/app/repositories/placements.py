from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Beneficiary, Placement


async def get_beneficiary(session: AsyncSession, beneficiary_id: int) -> Beneficiary | None:
    stmt = select(Beneficiary).where(Beneficiary.id == beneficiary_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_placements(
    session: AsyncSession,
    *,
    organization_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Placement]:
    stmt = select(Placement).order_by(Placement.created_at.desc(), Placement.id.desc())
    if organization_id is not None:
        stmt = stmt.where(Placement.organization_id == organization_id)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars())


async def create_placement(
    session: AsyncSession,
    *,
    beneficiary: Beneficiary,
    employer: str,
    role_title: str,
    skills: list[str],
    mentor_user_id: int | None = None,
) -> Placement:
    placement = Placement(
        beneficiary_id=beneficiary.id,
        organization_id=beneficiary.organization_id,
        employer=employer,
        role_title=role_title,
        skills=skills,
        mentor_user_id=mentor_user_id,
    )
    session.add(placement)
    await session.flush()
    return placement


async def update_placement_status(
    session: AsyncSession,
    placement_id: int,
    status: str,
) -> Placement | None:
    stmt = (
        update(Placement)
        .where(Placement.id == placement_id)
        .values(status=status)
        .returning(Placement)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()