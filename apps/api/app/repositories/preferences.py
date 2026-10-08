"""Data access for donor preferences (one row per donor)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DonorPreference


async def get_for_donor(
    session: AsyncSession, donor_id: int
) -> DonorPreference | None:
    result = await session.execute(
        select(DonorPreference).where(DonorPreference.donor_id == donor_id)
    )
    return result.scalar_one_or_none()


async def upsert(
    session: AsyncSession,
    *,
    donor_id: int,
    causes: list[str],
    budget: float | None,
    location: str | None,
) -> DonorPreference:
    """Create the donor's preference row, or replace the existing one.

    A PUT is a full replacement of the three preference fields, matching the
    schema (idempotent: calling it twice with the same body is a no-op apart
    from the updated_at timestamp).
    """
    preference = await get_for_donor(session, donor_id)
    if preference is None:
        preference = DonorPreference(donor_id=donor_id)
        session.add(preference)
    preference.causes = causes
    preference.budget = budget
    preference.location = location
    await session.flush()
    return preference