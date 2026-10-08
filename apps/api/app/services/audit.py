"""Tamper-evident audit trail service facade (Phase 4).

Routes depend on this service, which re-exports the hash-chain writer and
verifier from the repository layer. Keeping the concrete implementation in
``repositories/audit.py`` means the Phase 1/2 callers keep their imports
while new callers get one stable surface for everything audit-related.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.repositories import audit as audit_repo

entry_hash = audit_repo.entry_hash
log_action = audit_repo.log_action
verify_chain = audit_repo.verify_chain


async def record(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    organization_id: int | None = None,
    actor_id: int | None = None,
    note: str = "",
) -> AuditLog:
    """Append one chained audit row (alias of ``log_action``)."""
    return await log_action(
        session,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        organization_id=organization_id,
        actor_id=actor_id,
        note=note,
    )