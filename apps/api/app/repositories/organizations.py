"""Organization lookups. Orgs are lifecycle-light (no CRUD route yet); this
module exists so routes can verify a target org before writing to it."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Organization

ORG_TYPES = ("church", "mosque", "ministry", "ngo")


async def get(session: AsyncSession, organization_id: int) -> Organization | None:
    return (
        await session.execute(
            select(Organization).where(Organization.id == organization_id)
        )
    ).scalar_one_or_none()


async def exists(session: AsyncSession, organization_id: int) -> bool:
    return await get(session, organization_id) is not None


async def create(session: AsyncSession, *, name: str, org_type: str = "church") -> Organization:
    organization = Organization(name=name, org_type=org_type)
    session.add(organization)
    await session.flush()
    return organization


async def list_organizations(session: AsyncSession, *, limit: int = 200, offset: int = 0) -> list[Organization]:
    result = await session.execute(
        select(Organization).order_by(Organization.id).limit(limit).offset(offset)
    )
    return list(result.scalars())