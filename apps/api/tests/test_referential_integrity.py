"""Referential integrity tests for the foreign keys added in Phase 0 task 3.

These assert real database behaviour, not just that constraint names exist: an
orphan insert must fail, and each ondelete rule must actually fire. A constraint
declared but not enforced is exactly the gap this closes. The schema comes from
`alembic upgrade head` (see conftest), so these tests also fail if the migration
chain ever drifts from the ORM models.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import engine


async def _seed(conn) -> tuple[int, int, int]:
    """Insert one org, user and beneficiary; return their ids."""
    org_id = (
        await conn.execute(
            text(
                "INSERT INTO organizations (name, org_type) "
                "VALUES ('Test Org', 'church') RETURNING id"
            )
        )
    ).scalar()
    user_id = (
        await conn.execute(
            text(
                "INSERT INTO users (organization_id, email, full_name, role) "
                "VALUES (:o, 'donor@test.org', 'Donor', 'donor') RETURNING id"
            ),
            {"o": org_id},
        )
    ).scalar()
    beneficiary_id = (
        await conn.execute(
            text(
                "INSERT INTO beneficiaries (organization_id, user_id, household_size) "
                "VALUES (:o, :u, 3) RETURNING id"
            ),
            {"o": org_id, "u": user_id},
        )
    ).scalar()
    return org_id, user_id, beneficiary_id


async def test_orphan_donation_donor_is_rejected(clean_db):
    async with engine.begin() as conn:
        org_id, _, _ = await _seed(conn)
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO donations (donor_id, organization_id, amount) "
                    "VALUES (999999, :o, 100)"
                ),
                {"o": org_id},
            )


async def test_orphan_assistance_request_beneficiary_is_rejected(clean_db):
    async with engine.begin() as conn:
        org_id, _, _ = await _seed(conn)
        with pytest.raises(IntegrityError):
            await conn.execute(
                text(
                    "INSERT INTO assistance_requests "
                    "(beneficiary_id, organization_id, description, category) "
                    "VALUES (999999, :o, 'need', 'food')"
                ),
                {"o": org_id},
            )


async def test_orphan_program_organization_is_rejected(clean_db):
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO programs (organization_id, name, category) "
                    "VALUES (999999, 'Orphan Program', 'food')"
                )
            )


async def test_deleting_org_cascades_to_programs(clean_db):
    async with engine.begin() as conn:
        org_id, _, _ = await _seed(conn)
        await conn.execute(
            text(
                "INSERT INTO programs (organization_id, name, category) "
                "VALUES (:o, 'Food Bank', 'food')"
            ),
            {"o": org_id},
        )

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM organizations WHERE id = :o"), {"o": org_id}
        )

    async with engine.connect() as conn:
        remaining = (await conn.execute(text("SELECT count(*) FROM programs"))).scalar()
    assert remaining == 0, "programs should have cascaded on org delete"


async def test_deleting_beneficiary_cascades_to_requests_and_placements(clean_db):
    async with engine.begin() as conn:
        org_id, _, beneficiary_id = await _seed(conn)
        await conn.execute(
            text(
                "INSERT INTO assistance_requests "
                "(beneficiary_id, organization_id, description, category) "
                "VALUES (:b, :o, 'need help', 'food')"
            ),
            {"b": beneficiary_id, "o": org_id},
        )
        await conn.execute(
            text(
                "INSERT INTO placements "
                "(beneficiary_id, organization_id, employer, role_title) "
                "VALUES (:b, :o, 'Acme', 'Baker')"
            ),
            {"b": beneficiary_id, "o": org_id},
        )

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM beneficiaries WHERE id = :b"), {"b": beneficiary_id}
        )

    async with engine.connect() as conn:
        requests = (
            await conn.execute(text("SELECT count(*) FROM assistance_requests"))
        ).scalar()
        placements = (await conn.execute(text("SELECT count(*) FROM placements"))).scalar()
    assert requests == 0
    assert placements == 0


async def test_deleting_org_nulls_user_org_instead_of_deleting_user(clean_db):
    async with engine.begin() as conn:
        org_id, user_id, _ = await _seed(conn)

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM organizations WHERE id = :o"), {"o": org_id}
        )

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT organization_id FROM users WHERE id = :u"), {"u": user_id}
            )
        ).first()
    assert row is not None, "user must survive its organization being deleted"
    assert row[0] is None, "users.organization_id should be SET NULL"


async def test_donation_donor_restrict_blocks_user_deletion(clean_db):
    """Financial history must not vanish when a user row is removed (PRD §8)."""
    async with engine.begin() as conn:
        _, user_id, _ = await _seed(conn)
        await conn.execute(
            text(
                "INSERT INTO donations (donor_id, organization_id, amount) "
                "VALUES (:u, (SELECT id FROM organizations LIMIT 1), 50)"
            ),
            {"u": user_id},
        )

    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})


async def test_audit_log_outlives_its_actor(clean_db):
    """An audit row must survive the actor it records (PRD §22)."""
    async with engine.begin() as conn:
        org_id, user_id, _ = await _seed(conn)
        await conn.execute(
            text(
                "INSERT INTO audit_logs (organization_id, actor_id, action, "
                "entity_type, entity_id) "
                "VALUES (:o, :u, 'update', 'beneficiary', '1')"
            ),
            {"o": org_id, "u": user_id},
        )

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})

    async with engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM audit_logs"))).scalar()
        actor_id = (
            await conn.execute(text("SELECT actor_id FROM audit_logs LIMIT 1"))
        ).scalar()
    assert count == 1, "audit_logs row must survive its actor being deleted"
    assert actor_id is None, "audit_logs.actor_id should be SET NULL"


async def test_deleting_program_nulls_donation_program(clean_db):
    async with engine.begin() as conn:
        org_id, user_id, _ = await _seed(conn)
        program_id = (
            await conn.execute(
                text(
                    "INSERT INTO programs (organization_id, name, category) "
                    "VALUES (:o, 'Food Bank', 'food') RETURNING id"
                ),
                {"o": org_id},
            )
        ).scalar()
        donation_id = (
            await conn.execute(
                text(
                    "INSERT INTO donations "
                    "(donor_id, organization_id, program_id, amount) "
                    "VALUES (:u, :o, :p, 75) RETURNING id"
                ),
                {"u": user_id, "o": org_id, "p": program_id},
            )
        ).scalar()

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM programs WHERE id = :p"), {"p": program_id}
        )

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT program_id FROM donations WHERE id = :d"), {"d": donation_id}
            )
        ).first()
    assert row is not None, "donation must survive the program being deleted"
    assert row[0] is None, "donations.program_id should be SET NULL"


async def test_all_expected_foreign_keys_exist(clean_db):
    expected = {
            ("users", "organization_id"),
            ("programs", "organization_id"),
            ("beneficiaries", "organization_id"),
            ("beneficiaries", "user_id"),
            ("assistance_requests", "beneficiary_id"),
            ("assistance_requests", "organization_id"),
            ("donations", "donor_id"),
            ("donations", "organization_id"),
            ("donations", "program_id"),
            ("donations", "allocated_to_beneficiary_id"),
            ("placements", "beneficiary_id"),
            ("placements", "organization_id"),
            ("impact_events", "organization_id"),
            ("impact_rollups", "organization_id"),
            ("org_impact_configs", "organization_id"),
            ("audit_logs", "organization_id"),
            ("audit_logs", "actor_id"),
            ("deletion_requests", "organization_id"),
            ("deletion_requests", "beneficiary_id"),
            ("deletion_requests", "requester_id"),
            ("placements", "mentor_user_id"),
            ("sent_messages", "organization_id"),
            ("donor_preferences", "donor_id"),
        }
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT tc.table_name, kcu.column_name "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON tc.constraint_name = kcu.constraint_name "
                    " AND tc.table_schema = kcu.table_schema "
                    "WHERE tc.constraint_type = 'FOREIGN KEY' "
                    "  AND tc.table_schema = 'public'"
                )
            )
        ).fetchall()
    assert set(rows) == expected
