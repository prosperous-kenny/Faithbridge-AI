"""Phase 4 donation lifecycle, impact config and rollups.

Donations gained the lifecycle timestamps (paid/allocated/distributed) and an
optional allocation target beneficiary (SET NULL: a donation is financial
history that must survive the beneficiary row, PRD §8). The community impact
score needs per-organisation configurable weights and targets (PRD §15), and
the Celery/in-process rollup job materialises period totals into
``impact_rollups`` so dashboards do not re-scan the append-only feed.

Revision ID: c5d8a4f2e9b1
Revises: b7f3e9a2c41d
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5d8a4f2e9b1"
down_revision: str | None = "b7f3e9a2c41d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("donations", sa.Column("paid_at", sa.DateTime(), nullable=True))
    op.add_column("donations", sa.Column("allocated_at", sa.DateTime(), nullable=True))
    op.add_column("donations", sa.Column("distributed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "donations",
        sa.Column(
            "allocated_to_beneficiary_id",
            sa.Integer(),
            sa.ForeignKey("beneficiaries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_donations_allocated_to_beneficiary_id",
        "donations",
        ["allocated_to_beneficiary_id"],
    )

    op.create_table(
        "org_impact_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "families_weight", sa.Float(), nullable=False, server_default=sa.text("0.25")
        ),
        sa.Column(
            "education_weight", sa.Float(), nullable=False, server_default=sa.text("0.20")
        ),
        sa.Column(
            "employment_weight", sa.Float(), nullable=False, server_default=sa.text("0.20")
        ),
        sa.Column(
            "food_security_weight", sa.Float(), nullable=False, server_default=sa.text("0.20")
        ),
        sa.Column(
            "healthcare_weight", sa.Float(), nullable=False, server_default=sa.text("0.15")
        ),
        sa.Column("families_target", sa.Float(), nullable=False, server_default=sa.text("100")),
        sa.Column("education_target", sa.Float(), nullable=False, server_default=sa.text("100")),
        sa.Column("employment_target", sa.Float(), nullable=False, server_default=sa.text("100")),
        sa.Column(
            "food_security_target", sa.Float(), nullable=False, server_default=sa.text("100")
        ),
        sa.Column(
            "healthcare_target", sa.Float(), nullable=False, server_default=sa.text("100")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "impact_rollups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("metric", sa.String(length=50), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id",
            "period_start",
            "period_end",
            "metric",
            name="ix_impact_rollups_org_period_metric",
        ),
    )


def downgrade() -> None:
    op.drop_table("impact_rollups")
    op.drop_table("org_impact_configs")
    op.drop_index("ix_donations_allocated_to_beneficiary_id", table_name="donations")
    op.drop_column("donations", "allocated_to_beneficiary_id")
    op.drop_column("donations", "distributed_at")
    op.drop_column("donations", "allocated_at")
    op.drop_column("donations", "paid_at")