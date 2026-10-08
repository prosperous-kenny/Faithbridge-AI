"""Make the timestamp columns NOT NULL to match the ORM models.

The initial migration created created_at / updated_at / occurred_at as nullable
while the models declare them as non-Optional Mapped[datetime], which SQLAlchemy
maps to NOT NULL. The mismatch was invisible until the test suite stopped
rebuilding the schema with metadata.create_all; `alembic check` now catches it.

These columns carry server defaults of now(), so a NOT NULL constraint is the
correct guarantee for the audit trail (PRD §22). Existing NULLs are backfilled
first so the constraint can be applied safely.

Revision ID: 8e2b6d4f1a73
Revises: 4a7c1e92b0d5
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8e2b6d4f1a73"
down_revision: str | None = "4a7c1e92b0d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) pairs that the initial migration left nullable.
TIMESTAMP_COLUMNS = [
    ("organizations", "created_at"),
    ("organizations", "updated_at"),
    ("users", "created_at"),
    ("users", "updated_at"),
    ("programs", "created_at"),
    ("programs", "updated_at"),
    ("beneficiaries", "created_at"),
    ("beneficiaries", "updated_at"),
    ("assistance_requests", "created_at"),
    ("assistance_requests", "updated_at"),
    ("donations", "created_at"),
    ("donations", "updated_at"),
    ("placements", "created_at"),
    ("placements", "updated_at"),
    ("impact_events", "occurred_at"),
    ("impact_events", "created_at"),
    ("audit_logs", "created_at"),
]


def upgrade() -> None:
    for table, column in TIMESTAMP_COLUMNS:
        op.execute(
            sa.text(
                f'UPDATE "{table}" SET "{column}" = now() WHERE "{column}" IS NULL'
            )
        )
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(),
            nullable=False,
            existing_server_default=sa.text("now()"),
        )


def downgrade() -> None:
    for table, column in reversed(TIMESTAMP_COLUMNS):
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(),
            nullable=True,
            existing_server_default=sa.text("now()"),
        )
