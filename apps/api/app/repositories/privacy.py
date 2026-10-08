"""Data access for the privacy surface: consent and deletion requests (PRD §22).

"Deletion" is a governed workflow, not a raw DELETE: append-only tables
(impact feed, donation ledger, audit trail) must survive by design, so a
request here records the intent and an administrator resolves it by
anonymising the linked rows the trail must keep.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Beneficiary, DeletionRequest


async def get_beneficiary_for_user(
    session: AsyncSession, *, user_id: int
) -> Beneficiary | None:
    """The beneficiary record owned by a user who submitted a need.

    A user may have submitted to several organizations over time (each gets its
    own beneficiary row); consent is per row, so return the link that exists
    rather than one that must be fabricated.
    """
    result = await session.execute(
        select(Beneficiary)
        .where(Beneficiary.user_id == user_id)
        .order_by(Beneficiary.id)
    )
    return result.scalars().first()


async def get_beneficiary(session: AsyncSession, beneficiary_id: int) -> Beneficiary | None:
    return await session.get(Beneficiary, beneficiary_id)


async def record_consent(session: AsyncSession, beneficiary: Beneficiary) -> Beneficiary:
    """Stamp explicit consent (PRD §22: PII is shared only with consent).

    The timestamp is the same gate every PII-rendering surface already reads
    (``beneficiaries.consented_at``); nothing new is written here because the
    audit trail created by the route is the record of *who* consented *when*.
    """
    beneficiary.consented_at = func.now()
    await session.flush()
    return beneficiary


async def create_request(
    session: AsyncSession,
    *,
    organization_id: int | None,
    requester_id: int | None,
    beneficiary_id: int | None,
    scope: str,
    reason: str | None,
) -> DeletionRequest:
    request = DeletionRequest(
        organization_id=organization_id,
        requester_id=requester_id,
        beneficiary_id=beneficiary_id,
        scope=scope,
        reason=reason,
        status="pending",
    )
    session.add(request)
    await session.flush()
    return request


async def list_requests(
    session: AsyncSession,
    *,
    organization_id: int | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[DeletionRequest]:
    stmt = select(DeletionRequest).order_by(DeletionRequest.created_at.desc())
    if organization_id is not None:
        stmt = stmt.where(DeletionRequest.organization_id == organization_id)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars())


async def get_request(session: AsyncSession, request_id: int) -> DeletionRequest | None:
    return await session.get(DeletionRequest, request_id)