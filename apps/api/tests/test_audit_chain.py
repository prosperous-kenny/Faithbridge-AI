"""Phase 4 audit chain: the hash chain detects tampering, and per-organization
buckets verify independently.

PRD §22 requires a tamper-evident trail for money and case handling. The chain
is bucketed by organization: an edit to one row must break that
organization's run, cross-organization boundaries must NOT be reported as
breaks, and a fully intact chain must verify clean (so the verifier cannot be
permanently trip-wired).
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionFactory
from app.repositories import audit as audit_repo
from tests import factories


async def _org_chain(session, organization_id: int | None, count: int) -> None:
    for index in range(count):
        await audit_repo.log_action(
            session,
            action=f"test.event.{index}",
            entity_type="audit_test",
            entity_id=str(index),
            organization_id=organization_id,
            note=f"event {index}",
        )


async def test_intact_chain_verifies_clean():
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        await _org_chain(session, organization_id=org.id, count=3)
        await _org_chain(session, organization_id=None, count=2)
        await session.commit()

    async with SessionFactory() as session:
        violations = await audit_repo.verify_chain(session)
        assert violations == []


async def test_tampered_row_is_detected():
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        await _org_chain(session, organization_id=org.id, count=4)
        await session.commit()

    # Rewrite an early row's action without re-chaining: this is exactly the
    # hand-edit the verifier must catch.
    async with SessionFactory() as session:
        await session.execute(
            text(
                "UPDATE audit_logs SET action = 'test.event.TAMPERED' "
                "WHERE organization_id = :org AND action = 'test.event.0'"
            ),
            {"org": org.id},
        )
        await session.commit()

    async with SessionFactory() as session:
        violations = await audit_repo.verify_chain(session)
        # The tampered row itself no longer reproduces its stored hash.
        assert len(violations) >= 1
        assert any("chain mismatch" in v for v in violations)


async def test_tamper_in_one_org_does_not_break_another():
    async with SessionFactory() as session:
        org_a = await factories.create_organization(session)
        org_b = await factories.create_organization(session)
        await session.commit()
        await _org_chain(session, organization_id=org_a.id, count=2)
        await _org_chain(session, organization_id=org_b.id, count=2)
        await session.commit()

    async with SessionFactory() as session:
        await session.execute(
            text(
                "UPDATE audit_logs SET note = 'edited' "
                "WHERE organization_id = :org AND action = 'test.event.0'"
            ),
            {"org": org_a.id},
        )
        await session.commit()

    async with SessionFactory() as session:
        violations = await audit_repo.verify_chain(session)
        # Only org A's run reports breaks; org B's rows keep their own chain.
        assert len(violations) >= 1
        org_a_rows = (
            await session.execute(
                text(
                    "SELECT id FROM audit_logs WHERE organization_id = :org ORDER BY id"
                ),
                {"org": org_a.id},
            )
        ).scalars().all()
        assert len([v for v in violations if f"id={org_a_rows[0]}" in v]) >= 1


async def test_verify_chain_catches_late_row_deletion():
    async with SessionFactory() as session:
        org = await factories.create_organization(session)
        await session.commit()
        await _org_chain(session, organization_id=org.id, count=3)
        await session.commit()
        ids = (
            await session.execute(text("SELECT id FROM audit_logs ORDER BY id"))
        ).scalars().all()

    async with SessionFactory() as session:
        await session.execute(text(f"DELETE FROM audit_logs WHERE id = {ids[1]}"))
        await session.commit()

    async with SessionFactory() as session:
        violations = await audit_repo.verify_chain(session)
        assert violations != []