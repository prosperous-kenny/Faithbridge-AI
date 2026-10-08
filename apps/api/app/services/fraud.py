"""Fraud and abuse screening over submissions and the audit trail (PRD §22).

Two deterministic rules, both run synchronously when a request is created
(typed or voice) and both **flag only**: a submission always reaches the case
queue, because a false positive that hid a real need would be worse than a
human review. The output lands in ``fraud_flags`` for a leader to confirm or
dismiss.

Clock-sensitive comparisons use the database clock (``func.now()`` inside the
query) rather than the application's, so rows written by the API and rows
written by migrations/tests are compared on one timeline.
"""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AssistanceRequest, AuditLog, FraudFlag

RULE_DUPLICATE = "duplicate_request"
RULE_BURST = "submission_burst"

# Both audit actions count toward the velocity rule: a scripted abuser must
# not be able to switch channels and reset the window.
SUBMISSION_ACTIONS = (
    "assistance.request.submitted",
    "assistance.request.voice.submitted",
)

# A case is "open" while handlers are still expected to act on it; declined
# and fulfilled are terminal and do not count against a new submission.
OPEN_STATUSES = ("submitted", "triaged", "approved")

DUPLICATE_LOOKBACK_DAYS = 30
# Jaccard over normalized word sets: ≥ 0.8 means the two descriptions say the
# same thing in almost the same words.
DUPLICATE_SIMILARITY = 0.8

BURST_WINDOW_MINUTES = 10
BURST_THRESHOLD = 5


def _tokens(description: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", description.lower()))


def similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


async def screen_submission(
    session: AsyncSession,
    *,
    organization_id: int,
    beneficiary_id: int,
    description: str,
    actor_id: int,
    request_id: int | None = None,
) -> list[FraudFlag]:
    """Evaluate every rule against one fresh submission.

    Flags are added to the session but not committed: the caller commits them
    together with the request itself, so a case can never exist without its
    screening record (or vice versa).

    The caller must write this submission's audit row *before* calling, since
    the burst rule counts audit rows — including the one for this request.
    """
    flags: list[FraudFlag] = []

    duplicate_of = await _find_duplicate(
        session,
        organization_id=organization_id,
        beneficiary_id=beneficiary_id,
        description=description,
        exclude_id=request_id,
    )
    if duplicate_of is not None:
        flags.append(
            FraudFlag(
                organization_id=organization_id,
                request_id=request_id,
                rule=RULE_DUPLICATE,
                severity="high",
                detail=(
                    f"Description matches open request {duplicate_of.id} "
                    f"(similarity >= {DUPLICATE_SIMILARITY:.0%} within "
                    f"{DUPLICATE_LOOKBACK_DAYS} days)"
                ),
            )
        )

    burst_count = await _recent_submissions(session, actor_id=actor_id)
    if burst_count >= BURST_THRESHOLD:
        flags.append(
            FraudFlag(
                organization_id=organization_id,
                request_id=request_id,
                rule=RULE_BURST,
                severity="high",
                detail=(
                    f"{burst_count} submissions from this account within "
                    f"{BURST_WINDOW_MINUTES} minutes"
                ),
            )
        )

    for flag in flags:
        session.add(flag)
    return flags


async def _find_duplicate(
    session: AsyncSession,
    *,
    organization_id: int,
    beneficiary_id: int,
    description: str,
    exclude_id: int | None,
) -> AssistanceRequest | None:
    stmt = select(AssistanceRequest).where(
        AssistanceRequest.organization_id == organization_id,
        AssistanceRequest.beneficiary_id == beneficiary_id,
        AssistanceRequest.status.in_(OPEN_STATUSES),
        AssistanceRequest.created_at
        >= func.now() - cast(timedelta(days=DUPLICATE_LOOKBACK_DAYS), INTERVAL),
    )
    if exclude_id is not None:
        stmt = stmt.where(AssistanceRequest.id != exclude_id)
    candidates = (await session.execute(stmt)).scalars()

    incoming = _tokens(description)
    if not incoming:
        return None
    for candidate in candidates:
        if similarity(incoming, _tokens(candidate.description)) >= (
            DUPLICATE_SIMILARITY
        ):
            return candidate
    return None


async def _recent_submissions(session: AsyncSession, *, actor_id: int) -> int:
    count = (
        await session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action.in_(SUBMISSION_ACTIONS),
                AuditLog.actor_id == actor_id,
                AuditLog.created_at
                >= func.now() - cast(timedelta(minutes=BURST_WINDOW_MINUTES), INTERVAL),
            )
        )
    ).scalar()
    return int(count or 0)
