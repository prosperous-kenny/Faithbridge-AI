"""Donation ledger: pledges and the PRD §8 lifecycle (Phase 4).

A donor creates a pledge; a faith leader (of the receiving organization) or an
admin advances it along ``pledged → paid → allocated → distributed`` with a
tamper-evident audit row per transition and an impact event on distribution.
Donors can read their own rows only; the lifecycle endpoints are handler-only
because they move money on the receiving side.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.models import User
from app.db.session import get_session
from app.repositories import assistance as assistance_repo
from app.repositories import donations as donations_repo
from app.repositories import donations_ext as donations_ext_repo
from app.repositories import organizations as organizations_repo
from app.schemas.donations import (
    DonationIn,
    DonationListOut,
    DonationOut,
    DonationStatusUpdateIn,
)
from app.schemas.payments import PayDonationIn, PaymentResultOut, ReconcileOut
from app.services import donations as donation_service
from app.services import impact as impact_service
from app.services.audit import record as audit_record
from app.services.payments.provider import get_payment_provider
from app.services.payments.reconciliation import reconcile as reconcile_ledger
from app.workers.impact_rollup import impact_rollup

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

HANDLER_ROLES = (Role.FAITH_LEADER, Role.ADMIN)


@router.post("/", response_model=DonationOut, status_code=201,
             dependencies=[Depends(require_role(Role.DONOR))])
async def create_donation(
    payload: DonationIn,
    session: SessionDep,
    user: CurrentUser,
) -> DonationOut:
    """Record a donor's pledge against an organization.

    The pledge is the donor's commitment, so its creation is donor-only; the
    receiving side is who moves the money afterward. The target organization
    must exist (an FK failure would 500, and 404 is the honest answer).
    """
    if not await organizations_repo.exists(session, payload.organization_id):
        raise HTTPException(status_code=404, detail="Organization not found")

    donation = await donations_repo.create(
        session,
        donor_id=user.id,
        organization_id=payload.organization_id,
        amount=payload.amount,
        currency=payload.currency,
        program_id=payload.program_id,
    )
    # Money moving onto the ledger is audited even before it changes hands.
    await audit_record(
        session,
        action="donation.pledged",
        entity_type="donation",
        entity_id=str(donation.id),
        organization_id=donation.organization_id,
        actor_id=user.id,
        note=f"pledged {payload.amount} {payload.currency}",
    )
    await session.commit()
    await session.refresh(donation)
    return DonationOut.model_validate(donation)


@router.get("/", response_model=DonationListOut)
async def list_donations(
    session: SessionDep,
    # Passed as a Depends rather than a path/query argument so the role check
    # runs before any data is read, not after.
    donor: Annotated[User, Depends(require_role(Role.DONOR))],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DonationListOut:
    """Return the caller's own donations, or the whole ledger for an admin.

    A donor must never receive another donor's rows: the scoping is by the
    authenticated user id from the database, not by anything in the request,
    so there is no parameter a caller can alter to widen it. The admin branch
    is the one exception, and it exists because PRD §12 makes the system
    administrator the operator of the platform.
    """
    is_admin = donor.role == Role.ADMIN.value
    rows = await donations_repo.list_donations(
        session,
        donor_id=None if is_admin else donor.id,
        limit=limit,
        offset=offset,
    )
    items = [DonationOut.model_validate(row) for row in rows]
    return DonationListOut(items=items, count=len(items))


@router.patch(
    "/{donation_id}/status",
    response_model=DonationOut,
    dependencies=[Depends(require_role(*HANDLER_ROLES))],
)
async def update_donation_status(
    donation_id: int,
    payload: DonationStatusUpdateIn,
    session: SessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> DonationOut:
    """Advance a donation along the lifecycle, enforcing the allocation rules.

    Money movement is org-bound like case handling: a faith leader can only
    touch donations into their own organization. Allocation requires a target
    beneficiary in the same organization; distribution requires an allocation
    and records a ``donations_distributed`` impact event plus an audit row.
    Illegal transitions (e.g. pledged → distributed) are rejected before any
    write.
    """
    donation = await donations_repo.get(session, donation_id)
    if donation is None:
        raise HTTPException(status_code=404, detail="Donation not found")

    if user.organization_id is not None and donation.organization_id != user.organization_id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage donations for your own organization",
        )

    try:
        donation_service.assert_transition(donation.status, payload.status)
        if payload.status == "allocated":
            if payload.beneficiary_id is None:
                raise donation_service.AllocationError(
                    "Allocation requires a target beneficiary"
                )
            beneficiary = await assistance_repo.get_beneficiary(
                session, payload.beneficiary_id
            )
            if beneficiary is None:
                raise donation_service.AllocationError(
                    "Allocation target beneficiary does not exist"
                )
            donation_service.assert_allocatable(donation, beneficiary)
    except donation_service.AllocationError as exc:
        # The payload could not allocate money (missing/wrong target), which is
        # a client error, not a state problem.
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except donation_service.DonationLifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    donation = donation_service.apply_transition(
        donation,
        payload.status,
        allocated_to_beneficiary_id=payload.beneficiary_id if payload.status == "allocated" else None,
    )

    if payload.status == "distributed":
        await impact_service.record_event(
            session,
            organization_id=donation.organization_id,
            metric="donations_distributed",
            value=donation.amount,
        )

    await audit_record(
        session,
        action=f"donation.status.{payload.status}",
        entity_type="donation",
        entity_id=str(donation.id),
        organization_id=donation.organization_id,
        actor_id=user.id,
        note=f"{donation.amount} {donation.currency} moved to {payload.status}",
    )
    await session.commit()
    await session.refresh(donation)

    if payload.status == "distributed":
        background_tasks.add_task(impact_rollup, "monthly")

    return DonationOut.model_validate(donation)


@router.post(
    "/{donation_id}/pay",
    response_model=PaymentResultOut,
    dependencies=[Depends(require_role(Role.DONOR))],
)
async def pay_donation(
    donation_id: int,
    _payload: PayDonationIn,
    session: SessionDep,
    user: CurrentUser,
) -> PaymentResultOut:
    """Capture a pledge: create an intent on the provider and move to paid.

    Only the donor who pledged may capture it; a pledge may only move to paid
    once. The provider reference is stored for reconciliation (PRD §14).
    """
    donation = await donations_repo.get(session, donation_id)
    if donation is None:
        raise HTTPException(status_code=404, detail="Donation not found")
    if donation.donor_id != user.id:
        raise HTTPException(status_code=403, detail="You can only pay your own pledges")
    if donation.status != "pledged":
        raise HTTPException(status_code=409, detail=f"Cannot pay a {donation.status} donation")

    provider = get_payment_provider()
    intent = await provider.create_payment_intent(
        amount=donation.amount, currency=donation.currency
    )
    captured = await provider.capture_payment(intent.reference)
    await donations_ext_repo.set_provider_reference(session, donation.id, captured.reference)

    donation = donation_service.apply_transition(donation, "paid")
    await audit_record(
        session,
        action="donation.status.paid",
        entity_type="donation",
        entity_id=str(donation.id),
        organization_id=donation.organization_id,
        actor_id=user.id,
        note=f"{donation.amount} {donation.currency} paid via {provider.name}",
    )
    await session.commit()
    await session.refresh(donation)

    return PaymentResultOut(
        donation_id=donation.id,
        status=donation.status,
        provider=provider.name,
        provider_reference=captured.reference,
        amount=donation.amount,
        currency=donation.currency,
    )


@router.get(
    "/reconcile",
    response_model=ReconcileOut,
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def reconcile(session: SessionDep) -> ReconcileOut:
    """Point-in-time ledger vs provider reconciliation (PRD §14)."""
    result = await reconcile_ledger(session)
    return ReconcileOut.model_validate(result)