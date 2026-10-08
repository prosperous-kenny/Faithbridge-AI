from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SentMessage, User


async def record_message(
    session: AsyncSession,
    *,
    organization_id: int | None,
    channel: str,
    recipient_phone: str,
    template: str,
    status: str,
    provider_reference: str | None,
) -> SentMessage:
    msg = SentMessage(
        organization_id=organization_id,
        channel=channel,
        recipient_phone=recipient_phone,
        template=template,
        status=status,
        provider_reference=provider_reference,
    )
    session.add(msg)
    await session.flush()
    return msg


async def list_messages(
    session: AsyncSession,
    *,
    organization_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[SentMessage]:
    stmt = select(SentMessage).order_by(SentMessage.created_at.desc(), SentMessage.id.desc())
    if organization_id is not None:
        stmt = stmt.where(SentMessage.organization_id == organization_id)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars())


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()