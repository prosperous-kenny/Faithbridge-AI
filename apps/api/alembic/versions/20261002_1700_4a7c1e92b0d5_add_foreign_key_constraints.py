"""Add foreign key constraints across the nine PRD §20 tables.

Phase 0 task 3 requires referential integrity, not just integer columns named
after their parents. Every relationship is now enforced in the database:

- CASCADE where a child cannot outlive its parent (programs, beneficiaries,
  assistance requests, placements, impact events)
- SET NULL where the link is optional and the row must survive (a beneficiary
  without a login, an audit row whose actor is gone)
- RESTRICT on donations: financial history must never be deleted out from
  under the ledger (PRD §8)

Revision ID: 4a7c1e92b0d5
Revises: 9d8edb04c03c
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4a7c1e92b0d5"
down_revision: str | None = "9d8edb04c03c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, referenced table, ondelete)
CONSTRAINTS = [
    ("users", "organization_id", "organizations", "SET NULL"),
    ("programs", "organization_id", "organizations", "CASCADE"),
    ("beneficiaries", "organization_id", "organizations", "CASCADE"),
    ("beneficiaries", "user_id", "users", "SET NULL"),
    ("assistance_requests", "beneficiary_id", "beneficiaries", "CASCADE"),
    ("assistance_requests", "organization_id", "organizations", "CASCADE"),
    ("donations", "donor_id", "users", "RESTRICT"),
    ("donations", "organization_id", "organizations", "RESTRICT"),
    ("donations", "program_id", "programs", "SET NULL"),
    ("placements", "beneficiary_id", "beneficiaries", "CASCADE"),
    ("placements", "organization_id", "organizations", "CASCADE"),
    ("impact_events", "organization_id", "organizations", "CASCADE"),
    ("audit_logs", "organization_id", "organizations", "SET NULL"),
    ("audit_logs", "actor_id", "users", "SET NULL"),
]

NAMES = [
    "fk_users_organization_id",
    "fk_programs_organization_id",
    "fk_beneficiaries_organization_id",
    "fk_beneficiaries_user_id",
    "fk_assistance_requests_beneficiary_id",
    "fk_assistance_requests_organization_id",
    "fk_donations_donor_id",
    "fk_donations_organization_id",
    "fk_donations_program_id",
    "fk_placements_beneficiary_id",
    "fk_placements_organization_id",
    "fk_impact_events_organization_id",
    "fk_audit_logs_organization_id",
    "fk_audit_logs_actor_id",
]

# Indexes for the columns that are now join keys and are also filter targets.
INDEXES = [
    ("ix_users_organization_id", "users", ["organization_id"]),
    ("ix_programs_organization_id", "programs", ["organization_id"]),
    ("ix_beneficiaries_organization_id", "beneficiaries", ["organization_id"]),
    ("ix_beneficiaries_user_id", "beneficiaries", ["user_id"]),
    ("ix_assistance_requests_beneficiary_id", "assistance_requests", ["beneficiary_id"]),
    ("ix_assistance_requests_organization_id", "assistance_requests", ["organization_id"]),
    ("ix_assistance_requests_priority", "assistance_requests", ["priority"]),
    ("ix_donations_donor_id", "donations", ["donor_id"]),
    ("ix_donations_organization_id", "donations", ["organization_id"]),
    ("ix_donations_program_id", "donations", ["program_id"]),
    ("ix_placements_beneficiary_id", "placements", ["beneficiary_id"]),
    ("ix_placements_organization_id", "placements", ["organization_id"]),
    ("ix_impact_events_organization_id", "impact_events", ["organization_id"]),
    ("ix_impact_events_metric", "impact_events", ["metric"]),
    ("ix_audit_logs_organization_id", "audit_logs", ["organization_id"]),
    ("ix_audit_logs_actor_id", "audit_logs", ["actor_id"]),
]


def upgrade() -> None:
    for name, (table, column, parent, ondelete) in zip(NAMES, CONSTRAINTS, strict=True):
        op.create_foreign_key(
            constraint_name=name,
            source_table=table,
            referent_table=parent,
            local_cols=[column],
            remote_cols=["id"],
            ondelete=ondelete,
        )

    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)

    for name, (table, _column, _parent, _ondelete) in zip(
        reversed(NAMES), reversed(CONSTRAINTS), strict=True
    ):
        op.drop_constraint(name, table_name=table, type_="foreignkey")
