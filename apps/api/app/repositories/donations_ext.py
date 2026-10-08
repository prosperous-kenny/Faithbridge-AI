"""Update donations to record provider references for paid flows."""
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Donation


async def set_provider_reference(
    session: AsyncSession,
    donation_id: int,
    reference: str,
) -> Donation | None:
    stmt = (
        update(Donation)
        .where(Donation.id == donation_id)
        .values(provider_reference=reference)
        .returning(Donation)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()