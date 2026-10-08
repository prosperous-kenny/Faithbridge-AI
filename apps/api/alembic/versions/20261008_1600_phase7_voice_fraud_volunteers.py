"""Phase 7: volunteer profiles and fraud-flag inbox (PRD §14, §22).

The last feature schema of the plan:

* ``volunteers`` — who can help, with skills and availability slots, so
  volunteer matching has something to score (PRD §14 Phase 3).
* ``fraud_flags`` — the review inbox duplicate/anomaly screening writes to.
  Screening never blocks a submission; it records *why* something looked
  wrong for a leader to confirm or dismiss. SET NULL on both FKs like the
  audit trail: the evidence must outlive the rows it concerns.
"""

import sqlalchemy as sa

from alembic import op

revision = "b7e4f6a8c2d3"
down_revision = "a9b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "volunteers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column(
            "skills", sa.ARRAY(sa.String(length=50)), nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "availability", sa.ARRAY(sa.String(length=30)), nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="ix_volunteers_user_id"),
    )
    op.create_index("ix_volunteers_organization_id", "volunteers", ["organization_id"])

    op.create_table(
        "fraud_flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.Integer(), nullable=True),
        sa.Column("rule", sa.String(length=50), nullable=False),
        sa.Column(
            "severity", sa.String(length=20), nullable=False,
            server_default=sa.text("'medium'"),
        ),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["assistance_requests.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_fraud_flags_organization_id", "fraud_flags", ["organization_id"])
    op.create_index("ix_fraud_flags_request_id", "fraud_flags", ["request_id"])
    op.create_index("ix_fraud_flags_status", "fraud_flags", ["status"])


def downgrade() -> None:
    op.drop_index("ix_fraud_flags_status", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_request_id", table_name="fraud_flags")
    op.drop_index("ix_fraud_flags_organization_id", table_name="fraud_flags")
    op.drop_table("fraud_flags")
    op.drop_index("ix_volunteers_organization_id", table_name="volunteers")
    op.drop_table("volunteers")
