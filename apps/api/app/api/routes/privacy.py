"""Privacy surface: consent recording and data-deletion requests (PRD §22).

Consent is the gate every PII renderer already reads — ``beneficiaries.consented_at``
— and this surface is where it is captured explicitly. Deletion is a governed
workflow: the request is recorded tamper-evidently and an administrator
resolves it; raw DELETEs are deliberately absent so the impact feed, donation
ledger and audit trail never silently lose history.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.session import get_session
from app.repositories import privacy as privacy_repo
from app.schemas.privacy import (
    ConsentOut,
    DeletionRequestIn,
    DeletionRequestListOut,
    DeletionRequestOut,
)
from app.services.audit import record as audit_record

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

HANDLER_ROLES = (Role.FAITH_LEADER, Role.ADMIN)
# Who may raise a deletion request for themselves. Every registered role can be
# a beneficiary or a donor; the request is anchored to their own rows, no
# matter which role registered the account.
SELF_SERVICE_ROLES = (Role.COMMUNITY_MEMBER, Role.DONOR, Role.FAITH_LEADER, Role.ADMIN)


def _beneficiary_org(beneficiary) -> int:
    return beneficiary.organization_id


@router.post(
    "/consent",
    response_model=ConsentOut,
    status_code=200,
    dependencies=[Depends(require_role(*SELF_SERVICE_ROLES))],
)
async def record_self_consent(
    session: SessionDep,
    user: CurrentUser,
) -> ConsentOut:
    """Record explicit consent for the caller's own beneficiary record.

    PII is rendered only where ``consented_at`` is set (PRD §22); this endpoint
    is the signed moment that sets it. Requires the caller to have a
    beneficiary record (they submitted a need); otherwise there is nothing to
    consent for.
    """
    beneficiary = await privacy_repo.get_beneficiary_for_user(session, user_id=user.id)
    if beneficiary is None:
        raise HTTPException(
            status_code=404,
            detail="No beneficiary record exists for this account",
        )
    await privacy_repo.record_consent(session, beneficiary)
    await audit_record(
        session,
        action="privacy.consent.recorded",
        entity_type="beneficiary",
        entity_id=str(beneficiary.id),
        organization_id=beneficiary.organization_id,
        actor_id=user.id,
        note="self-service consent",
    )
    await session.commit()
    await session.refresh(beneficiary)
    return ConsentOut(
        beneficiary_id=beneficiary.id,
        organization_id=beneficiary.organization_id,
        consented_at=beneficiary.consented_at,
    )


@router.post(
    "/consent/{beneficiary_id}",
    response_model=ConsentOut,
    status_code=200,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def record_handler_consent(
    beneficiary_id: int,
    session: SessionDep,
    user: CurrentUser,
) -> ConsentOut:
    """Record consent on behalf of a person assisted by this organization.

    Faith leaders capture explicit consent during in-person intake for someone
    without a portal account; the organization-scope check keeps leaders to
    their own org, matching every other handler surface.
    """
    beneficiary = await privacy_repo.get_beneficiary(session, beneficiary_id)
    if beneficiary is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    if (
        user.organization_id is not None
        and beneficiary.organization_id != user.organization_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only record consent in your own organization",
        )
    await privacy_repo.record_consent(session, beneficiary)
    await audit_record(
        session,
        action="privacy.consent.recorded",
        entity_type="beneficiary",
        entity_id=str(beneficiary.id),
        organization_id=beneficiary.organization_id,
        actor_id=user.id,
        note="consent captured by case handler",
    )
    await session.commit()
    await session.refresh(beneficiary)
    return ConsentOut(
        beneficiary_id=beneficiary.id,
        organization_id=beneficiary.organization_id,
        consented_at=beneficiary.consented_at,
    )


@router.post(
    "/data-deletion",
    response_model=DeletionRequestOut,
    status_code=201,
    dependencies=[Depends(require_role(*SELF_SERVICE_ROLES))],
)
async def request_data_deletion(
    payload: DeletionRequestIn,
    session: SessionDep,
    user: CurrentUser,
) -> DeletionRequestOut:
    """Request deletion of the caller's own data (PRD §22).

    The request enters a governed inbox (an administrator resolves it); the row
    and its audit trail survive, because deleting history out from under the
    tamper-evident ledger is exactly what §22 forbids.
    """
    beneficiary = await privacy_repo.get_beneficiary_for_user(session, user_id=user.id)
    request = await privacy_repo.create_request(
        session,
        organization_id=user.organization_id,
        requester_id=user.id,
        beneficiary_id=beneficiary.id if beneficiary is not None else None,
        scope=payload.scope,
        reason=payload.reason,
    )
    await audit_record(
        session,
        action="privacy.deletion.requested",
        entity_type="deletion_request",
        entity_id=str(request.id),
        organization_id=user.organization_id,
        actor_id=user.id,
        note=f"scope={payload.scope}",
    )
    await session.commit()
    await session.refresh(request)
    return DeletionRequestOut.model_validate(request)


@router.post(
    "/data-deletion/{beneficiary_id}",
    response_model=DeletionRequestOut,
    status_code=201,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def request_data_deletion_for_beneficiary(
    beneficiary_id: int,
    payload: DeletionRequestIn,
    session: SessionDep,
    user: CurrentUser,
) -> DeletionRequestOut:
    """Raise a deletion request on behalf of an assisted person.

    Handlers are scoped to their own organization so a leader cannot lodge a
    request against another org's beneficiary.
    """
    beneficiary = await privacy_repo.get_beneficiary(session, beneficiary_id)
    if beneficiary is None:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
    if (
        user.organization_id is not None
        and beneficiary.organization_id != user.organization_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You can only raise requests in your own organization",
        )
    request = await privacy_repo.create_request(
        session,
        organization_id=beneficiary.organization_id,
        requester_id=user.id,
        beneficiary_id=beneficiary.id,
        scope=payload.scope,
        reason=payload.reason,
    )
    await audit_record(
        session,
        action="privacy.deletion.requested",
        entity_type="deletion_request",
        entity_id=str(request.id),
        organization_id=beneficiary.organization_id,
        actor_id=user.id,
        note=f"scope={payload.scope} on behalf of beneficiary {beneficiary.id}",
    )
    await session.commit()
    await session.refresh(request)
    return DeletionRequestOut.model_validate(request)


@router.get(
    "/data-deletion",
    response_model=DeletionRequestListOut,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def list_data_deletion_requests(
    session: SessionDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DeletionRequestListOut:
    """The deletion inbox. Leaders see their own org's requests; a platform
    admin sees every org's."""
    rows = await privacy_repo.list_requests(
        session,
        organization_id=user.organization_id,
        limit=limit,
        offset=offset,
    )
    return DeletionRequestListOut(
        items=[DeletionRequestOut.model_validate(row) for row in rows],
        count=len(rows),
    )