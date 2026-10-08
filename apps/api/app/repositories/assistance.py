"""Data access for assistance requests and the beneficiary data attached to them."""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import AssistanceRequest, Beneficiary

PRIORITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# The lifecycle rules live in app/services/assistance.py, not here: repositories
# move rows, the service owns business state transitions.


def _priority_weight_expr():
    return case(
        (AssistanceRequest.priority == "critical", 4),
        (AssistanceRequest.priority == "high", 3),
        (AssistanceRequest.priority == "medium", 2),
        else_=1,
    )


async def get_or_create_beneficiary(
    session: AsyncSession,
    *,
    user_id: int,
    organization_id: int,
) -> Beneficiary:
    """The beneficiary behind an authenticated submitter, creating it on first
    submission.

    Submitting a need is treated as consent to share the *case* with the
    organization handling it (PRD §22): without that, no handler could ever see
    who is asking for help. The explicit consent flag is set here so later
    callers (including donor-facing code) keep using the same gate.
    """
    existing = (
        await session.execute(
            select(Beneficiary).where(
                Beneficiary.user_id == user_id,
                Beneficiary.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    beneficiary = Beneficiary(
        organization_id=organization_id,
        user_id=user_id,
        household_size=1,
        consented_at=func.now(),
    )
    session.add(beneficiary)
    await session.flush()
    return beneficiary


async def get_beneficiary(session: AsyncSession, beneficiary_id: int) -> Beneficiary | None:
    return (
        await session.execute(
            select(Beneficiary).where(Beneficiary.id == beneficiary_id)
        )
    ).scalar_one_or_none()


async def create_request(
    session: AsyncSession,
    *,
    beneficiary_id: int,
    organization_id: int,
    description: str,
    category: str,
    urgency_score: int,
    priority: str,
) -> AssistanceRequest:
    request = AssistanceRequest(
        beneficiary_id=beneficiary_id,
        organization_id=organization_id,
        description=description,
        category=category,
        urgency_score=urgency_score,
        priority=priority,
        status="submitted",
    )
    session.add(request)
    await session.flush()
    return request


async def get_request(
    session: AsyncSession, request_id: int
) -> AssistanceRequest | None:
    """Fetch a request with everything a case detail needs preloaded."""
    stmt = (
        select(AssistanceRequest)
        .where(AssistanceRequest.id == request_id)
        .options(
            selectinload(AssistanceRequest.beneficiary).selectinload(Beneficiary.user)
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_status(
    session: AsyncSession, request: AssistanceRequest, status: str
) -> AssistanceRequest:
    request.status = status
    await session.flush()
    return request


async def list_requests(
    session: AsyncSession,
    *,
    limit: int = 200,
    offset: int = 0,
    priority: str | None = None,
    status: str | None = None,
    sort: str = "newest",
    organization_id: int | None = None,
) -> list[AssistanceRequest]:
    """List assistance requests with their beneficiary loaded.

    The beneficiary and its linked user are eagerly fetched because every
    caller of this read needs them (consent-gated PII rendering), and N+1
    lazy loads inside a response model are how these queries get expensive.

    ``sort="priority"`` orders by the triage band (critical first) so the
    faith-leader queue can show the most urgent work without client-side
    re-sorting; ``sort="newest"`` keeps the plain chronological view.
    """
    stmt = (
        select(AssistanceRequest)
        .options(
            selectinload(AssistanceRequest.beneficiary).selectinload(Beneficiary.user)
        )
        .limit(limit)
        .offset(offset)
    )
    if priority is not None:
        stmt = stmt.where(AssistanceRequest.priority == priority)
    if status is not None:
        stmt = stmt.where(AssistanceRequest.status == status)
    if organization_id is not None:
        stmt = stmt.where(AssistanceRequest.organization_id == organization_id)

    if sort == "priority":
        stmt = stmt.order_by(
            _priority_weight_expr().desc(),
            AssistanceRequest.created_at.desc(),
            AssistanceRequest.id.desc(),
        )
    else:
        stmt = stmt.order_by(
            AssistanceRequest.created_at.desc(), AssistanceRequest.id.desc()
        )

    result = await session.execute(stmt)
    return list(result.scalars().unique())