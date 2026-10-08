"""Fraud-flag review: confirming or dismissing what screening recorded (PRD §22).

Flags are written at submission time by ``services/fraud.py``; this router is
the human side of the loop — a leader inspects the queue, decides, and the
decision itself goes into the tamper-evident audit trail.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.models import FraudFlag
from app.db.session import get_session
from app.repositories import audit as audit_repo
from app.schemas.fraud import FraudFlagOut, FraudFlagUpdateIn

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ReviewRoles = (Role.FAITH_LEADER, Role.ADMIN)


@router.get(
    "/flags",
    response_model=list[FraudFlagOut],
    dependencies=[Depends(require_role(*ReviewRoles))],
)
async def list_flags(
    session: SessionDep,
    user: CurrentUser,
    status: Annotated[
        Literal["open", "confirmed", "dismissed"] | None, Query()
    ] = None,
    rule: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FraudFlagOut]:
    """Queue of pending abuse signals, newest first.

    Organization-bound leaders see only their own org's flags; a platform
    admin without an organization sees every org, mirroring the case-list
    rule.
    """
    stmt = select(FraudFlag).order_by(
        FraudFlag.created_at.desc(), FraudFlag.id.desc()
    )
    if user.organization_id is not None:
        stmt = stmt.where(FraudFlag.organization_id == user.organization_id)
    if status is not None:
        stmt = stmt.where(FraudFlag.status == status)
    if rule is not None:
        stmt = stmt.where(FraudFlag.rule == rule)
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars()
    return [FraudFlagOut.model_validate(row) for row in rows]


@router.patch(
    "/flags/{flag_id}",
    response_model=FraudFlagOut,
    dependencies=[Depends(require_role(*ReviewRoles))],
)
async def update_flag(
    flag_id: int,
    payload: FraudFlagUpdateIn,
    session: SessionDep,
    user: CurrentUser,
) -> FraudFlagOut:
    """Record a reviewer's decision on one flag.

    The decision is an audit event like any other state change, so the
    trail shows not only what screening caught but who cleared it.
    """
    flag = (
        await session.execute(select(FraudFlag).where(FraudFlag.id == flag_id))
    ).scalar_one_or_none()
    if flag is None:
        raise HTTPException(status_code=404, detail="Fraud flag not found")
    if (
        user.organization_id is not None
        and flag.organization_id != user.organization_id
    ):
        raise HTTPException(
            status_code=403, detail="You can only review flags in your own organization"
        )

    flag.status = payload.status
    await audit_repo.log_action(
        session,
        action=f"fraud.flag.status.{payload.status}",
        entity_type="fraud_flag",
        entity_id=str(flag.id),
        organization_id=flag.organization_id,
        actor_id=user.id,
        note=flag.detail,
    )
    await session.commit()
    await session.refresh(flag)
    return FraudFlagOut.model_validate(flag)
