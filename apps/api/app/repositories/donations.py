"""Donation ledger persistence (Phase 4).

Adds the write path alongside Phase 1's read-only ``list_donations``: create a
pledge and fetch a single row for lifecycle transitions. The lifecycle and
allocation rules live in ``app/services/donations.py`` so the route never has
to reason about money moving.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Donation


async def create(
    session: AsyncSession,
    *,
    donor_id: int,
    organization_id: int,
    amount: int,
    currency: str = "USD",
    program_id: int | None = None,
) -> Donation:
    donation = Donation(
        donor_id=donor_id,
        organization_id=organization_id,
        program_id=program_id,
        amount=amount,
        currency=currency,
        status="pledged",
    )
    session.add(donation)
    await session.flush()
    return donation


async def get(session: AsyncSession, donation_id: int) -> Donation | None:
    stmt = select(Donation).where(Donation.id == donation_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_donations(
    session: AsyncSession,
    *,
    donor_id: int | None = None,
    organization_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[Donation]:
    stmt = select(Donation).order_by(Donation.created_at.desc(), Donation.id.desc())
    if donor_id is not None:
        stmt = stmt.where(Donation.donor_id == donor_id)
    if organization_id is not None:
        stmt = stmt.where(Donation.organization_id == organization_id)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars())


async def list_distributed(
    session: AsyncSession,
    *,
    organization_id: int | None = None,
    start=None,
    end=None,
) -> list[Donation]:
    """Distributed donations in an optional half-open ``[start, end)`` window
    — the ledger side of the "donations distributed reconcile with impact"
    guarantee."""
    stmt = select(Donation).where(Donation.status == "distributed")
    if organization_id is not None:
        stmt = stmt.where(Donation.organization_id == organization_id)
    if start is not None:
        stmt = stmt.where(Donation.distributed_at >= start)
    if end is not None:
        stmt = stmt.where(Donation.distributed_at < end)
    result = await session.execute(stmt)
    return list(result.scalars())