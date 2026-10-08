"""Tamper-evident audit trail writes (PRD §22).

This is a *chain*, not a log: each entry's hash is derived from the previous
entry's hash plus its own immutable fields, so altering any row invalidates
every later hash in the run.

The chain is bucketed by ``organization_id`` so one organization's trail can
be verified without reading another's rows, and system-level rows (no org)
form their own chain.

Verification re-runs the deterministic hash computation over the stored rows
and reports every position where the stored hash no longer matches.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


def entry_hash(previous_hash: str, *, action: str, entity_type: str, entity_id: str, note: str) -> str:
    """Deterministic hash of an entry's immutable fields, chained to its
    predecessor. Any caller with the same inputs reproduces the same digest,
    which is what makes tampering detectable."""
    payload = (
        f"{previous_hash}\0{action}\0{entity_type}\0{entity_id}\0{note}".encode()
    )
    return hashlib.sha256(payload).hexdigest()


async def _last_hash(session: AsyncSession, organization_id: int | None) -> str | None:
    stmt = (
        select(AuditLog.entry_hash)
        .order_by(AuditLog.id.desc())
        .limit(1)
    )
    # IS NULL for the system chain, equality otherwise: `col IS $1` is a
    # Postgres syntax error, so the two cases must be rendered differently.
    if organization_id is None:
        stmt = stmt.where(AuditLog.organization_id.is_(None))
    else:
        stmt = stmt.where(AuditLog.organization_id == organization_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def log_action(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    organization_id: int | None = None,
    actor_id: int | None = None,
    note: str = "",
) -> AuditLog:
    """Append one audit row, chaining its hash to the latest row in the same
    organization's run. ``created_at`` is intentionally excluded from the
    digest: the server timestamps the row, which makes the hash order the
    chain without needing the writer to guess a clock."""
    await session.flush()  # ensure prior writes in this txn are visible
    previous = await _last_hash(session, organization_id) or ""
    entry = AuditLog(
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        note=note,
        entry_hash=entry_hash(
            previous, action=action, entity_type=entity_type, entity_id=str(entity_id), note=note
        ),
    )
    session.add(entry)
    await session.flush()
    return entry


async def verify_chain(session: AsyncSession) -> list[str]:
    """Recompute each organization's chain and report broken links.

    Returns a list of human-readable violations; [] means the chain is intact.
    """
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.organization_id, AuditLog.id)
    )
    rows = list(result.scalars())

    violations: list[str] = []
    run_prev: str | None = None
    previous_org: int | None | object = object()
    for entry in rows:
        # Each organization's run chains from the empty string (see
        # ``_last_hash``); crossing into a new org must reset the link,
        # otherwise the bucket boundary is misreported as a break.
        if entry.organization_id != previous_org:
            run_prev = None
            previous_org = entry.organization_id
        expected = entry_hash(
            run_prev or "",
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            note=entry.note or "",
        )
        if entry.entry_hash != expected:
            violations.append(
                f"audit_logs id={entry.id} chain mismatch (stored {entry.entry_hash}, expected {expected})"
            )
        run_prev = entry.entry_hash
    return violations