"""Phase 3 matching schema: richer programs and donor preferences.

Programs gained the fields the matching engine ranks on (description,
location, budget_needed) and a soft-retirement flag (is_active) so a program
can leave donor matching and the public list without deleting rows that
donations point at (PRD §8). Donor preferences (PRD Use Case 2) are one row
per donor holding the stated causes, budget and location.

Revision ID: b7f3e9a2c41d
Revises: a1c2e4f60891
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7f3e9a2c41d"
down_revision: str | None = "a1c2e4f60891"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("description", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "programs",
        sa.Column("location", sa.String(length=100), nullable=True),
    )
    op.add_column("programs", sa.Column("budget_needed", sa.Integer(), nullable=True))
    op.add_column(
        "programs",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "donor_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "donor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "causes",
            sa.ARRAY(sa.String(length=50)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
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


def downgrade() -> None:
    op.drop_table("donor_preferences")
    op.drop_column("programs", "is_active")
    op.drop_column("programs", "budget_needed")
    op.drop_column("programs", "location")
    op.drop_column("programs", "description")