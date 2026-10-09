"""Assistance request submission and case handling."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.session import get_session
from app.repositories import assistance as assistance_repo
from app.repositories import audit as audit_repo
from app.repositories import organizations as organizations_repo
from app.schemas.assistance import (
    AssistanceRequestDetail,
    AssistanceRequestIn,
    AssistanceRequestOut,
    BeneficiaryOut,
    PersonOut,
    Priority,
    StatusUpdateIn,
)
from app.services import fraud as fraud_service
from app.services import impact as impact_service
from app.services.ai_client import ai_service_available, classify_need
from app.services.assistance import LifecycleError, assert_transition
from app.workers.tasks import notify_new_critical_request, rescore_request

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Case handlers. Donors are deliberately absent: PRD §22 requires that
# beneficiary PII is never exposed to donor-facing endpoints, and the case list
# is the endpoint that carries it.
READ_ROLES = (Role.FAITH_LEADER, Role.ADMIN)
# Submitting a need is what PRD §6 assigns to Community Members. PRD §20 gives
# each user a single role, so a donor who is also in need needs a
# community_member account to submit.
SUBMIT_ROLES = (Role.COMMUNITY_MEMBER, Role.FAITH_LEADER, Role.ADMIN)

VALID_CATEGORIES = frozenset(
    {"food", "education", "medical", "employment", "housing", "emergency"}
)
VALID_PRIORITIES = frozenset({"critical", "high", "medium", "low"})


def _validated_classification(payload: dict) -> dict:
    """Fail closed on a noisy AI response.

    The AI service is a network dependency whose output lives on the trust
    boundary: an unparseable or out-of-range classification must never reach
    the database or a client as if it were valid. If the payload does not
    satisfy the same contract the schema declares, the request fails closed.
    """
    category = payload.get("category")
    urgency_score = payload.get("urgency_score")
    priority = payload.get("priority")
    if (
        category not in VALID_CATEGORIES
        or not isinstance(urgency_score, int)
        or not 0 <= urgency_score <= 100
        or priority not in VALID_PRIORITIES
    ):
        raise HTTPException(
            status_code=503,
            detail="AI service returned an invalid classification",
        )
    return payload


@router.post(
    "/requests",
    response_model=AssistanceRequestOut,
    status_code=201,
    dependencies=[Depends(require_role(*SUBMIT_ROLES))],
)
async def create_request(
    payload: AssistanceRequestIn,
    session: SessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> AssistanceRequestOut:
    """Submit a need and persist it with a synchronous AI classification.

    Submitting to an organization the caller does not belong to would drop the
    case into a queue its members cannot see and mine, so org-bound submitters
    are restricted to their own organization. A platform admin without an
    organization may post to any, since they hold every handler role anyway.
    """
    if user.organization_id is not None and payload.organization_id != user.organization_id:
        raise HTTPException(
            status_code=403,
            detail="You can only submit requests to your own organization",
        )

    # A request must land in a queue that exists. Without this the insert would
    # hit the foreign key and surface as an opaque 500; a missing organization is
    # a client error, so it is answered as one (same guard the donations route uses).
    if not await organizations_repo.exists(session, payload.organization_id):
        raise HTTPException(status_code=404, detail="Organization not found")

    if not await ai_service_available():
        raise HTTPException(status_code=503, detail="AI service unavailable")
    classification = _validated_classification(
        await classify_need(payload.description)
    )

    beneficiary = await assistance_repo.get_or_create_beneficiary(
        session, user_id=user.id, organization_id=payload.organization_id
    )
    request = await assistance_repo.create_request(
        session,
        beneficiary_id=beneficiary.id,
        organization_id=payload.organization_id,
        description=payload.description,
        category=classification["category"],
        urgency_score=classification["urgency_score"],
        priority=classification["priority"],
    )
    await audit_repo.log_action(
        session,
        action="assistance.request.submitted",
        entity_type="assistance_request",
        entity_id=str(request.id),
        organization_id=request.organization_id,
        actor_id=user.id,
    )
    # Flag-only screening (Phase 7): the request always reaches the queue;
    # anything suspicious is recorded for human review, never blocked.
    await fraud_service.screen_submission(
        session,
        organization_id=request.organization_id,
        beneficiary_id=request.beneficiary_id,
        description=request.description,
        actor_id=user.id,
        request_id=request.id,
    )
    await session.commit()

    background_tasks.add_task(notify_new_critical_request, request.id)

    return AssistanceRequestOut(
        id=request.id,
        organization_id=request.organization_id,
        description=request.description,
        category=request.category,
        urgency_score=request.urgency_score,
        priority=request.priority,
        status=request.status,
        created_at=request.created_at,
    )


@router.get(
    "/requests",
    response_model=list[AssistanceRequestDetail],
    dependencies=[Depends(require_role(*READ_ROLES))],
)
async def list_requests(
    session: SessionDep,
    user: CurrentUser,
    priority: Annotated[Priority | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    sort: Annotated[Literal["newest", "priority"], Query()] = "newest",
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AssistanceRequestDetail]:
    """List assistance requests, exposing beneficiary PII only where consent
    exists (PRD §22).

    The role guard above is what stops a donor from reaching this data at all;
    consent is the second, independent check for callers who *are* allowed in.
    Organization-bound handlers see only their own org's queue; a platform
    admin without an organization sees every org (their authority spans orgs).
    ``sort`` defaults to newest-first; ``sort=priority`` surfaces critical
    cases first for the triage queue.
    """
    items = await assistance_repo.list_requests(
        session,
        limit=limit,
        offset=offset,
        priority=priority,
        status=status or None,
        sort=sort,
        organization_id=user.organization_id,
    )
    return [_to_detail(item) for item in items]


@router.patch(
    "/requests/{request_id}/status",
    response_model=AssistanceRequestOut,
    dependencies=[Depends(require_role(*READ_ROLES))],
)
async def update_request_status(
    request_id: int,
    payload: StatusUpdateIn,
    session: SessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> AssistanceRequestOut:
    """Advance a case along the lifecycle, recording each transition in the
    tamper-evident audit trail.

    Illegal transitions (e.g. jumping straight from ``submitted`` to
    ``fulfilled``, or touching a terminal state) are rejected before any write.
    Moving a request into ``triaged`` queues a background re-classification,
    because case info known at triage time can sharpen the rating the
    submission alone produced.
    """
    request = await assistance_repo.get_request(session, request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Assistance request not found")

    if (
        user.organization_id is not None
        and request.organization_id != user.organization_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only manage requests in your own organization",
        )

    try:
        assert_transition(request.status, payload.status)
    except LifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    await assistance_repo.update_status(session, request, payload.status)

    # A fulfilled case is a family supported (PRD §8 impact feed): the
    # append-only event is written by the domain action that reached the end
    # of the lifecycle, never by hand.
    if payload.status == "fulfilled":
        await impact_service.record_event(
            session,
            organization_id=request.organization_id,
            metric="families_supported",
            value=1,
        )

    await audit_repo.log_action(
        session,
        action=f"assistance.request.status.{payload.status}",
        entity_type="assistance_request",
        entity_id=str(request.id),
        organization_id=request.organization_id,
        actor_id=user.id,
        note=payload.note,
    )
    await session.commit()

    if payload.status == "triaged":
        background_tasks.add_task(rescore_request, request.id)

    return AssistanceRequestOut(
        id=request.id,
        organization_id=request.organization_id,
        description=request.description,
        category=request.category,
        urgency_score=request.urgency_score,
        priority=request.priority,
        status=request.status,
        created_at=request.created_at,
    )


def _to_detail(item) -> AssistanceRequestDetail:
    beneficiary = item.beneficiary
    consented = beneficiary.consented_at is not None
    person = None
    if consented and beneficiary.user is not None:
        person = PersonOut(
            id=beneficiary.user.id,
            full_name=beneficiary.user.full_name,
            email=beneficiary.user.email,
        )
    return AssistanceRequestDetail(
        id=item.id,
        description=item.description,
        category=item.category,
        urgency_score=item.urgency_score,
        priority=item.priority,
        status=item.status,
        created_at=item.created_at,
        beneficiary=BeneficiaryOut(
            id=beneficiary.id,
            organization_id=beneficiary.organization_id,
            household_size=beneficiary.household_size,
            consented=consented,
            person=person,
        ),
    )