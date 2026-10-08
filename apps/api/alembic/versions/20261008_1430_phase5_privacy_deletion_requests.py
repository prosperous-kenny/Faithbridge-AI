"""Phase 5: data-deletion workflow backend (PRD §22).

Privacy is Phase 5's concern: while append-only tables (impact feed, donation
ledger, audit trail) must survive by design, PRD §22 still promises that
*beneficiaries may edit or request deletion*. This migration creates the
governed surface for that promise: a ``deletion_requests`` inbox an
administrator works through, so a deletion is a reviewed act performed against
a record, not a raw DELETE that would silently break the tamper-evident trail.
"""

import sqlalchemy as sa

from alembic import op

revision = "f6c3a8d1b2e7"
down_revision = "c5d8a4f2e9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deletion_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("requester_id", sa.Integer(), nullable=True),
        sa.Column("beneficiary_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["beneficiary_id"], ["beneficiaries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deletion_requests_organization_id", "deletion_requests", ["organization_id"]
    )
    op.create_index(
        "ix_deletion_requests_beneficiary_id", "deletion_requests", ["beneficiary_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_deletion_requests_beneficiary_id", table_name="deletion_requests")
    op.drop_index("ix_deletion_requests_organization_id", table_name="deletion_requests")
    op.drop_table("deletion_requests")