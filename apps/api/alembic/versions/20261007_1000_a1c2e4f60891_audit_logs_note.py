"""Add a free-text note to audit log entries.

Case handlers attach an optional reason to a status transition (e.g. why a
request was declined). The note is part of the tamper-evident chain (PRD §22),
so it must be stored on the same row as the action it documents rather than
reconstructed from prose later.

Revision ID: a1c2e4f60891
Revises: a1f5c2e7d904
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2e4f60891"
down_revision: str | None = "a1f5c2e7d904"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("note", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_logs", "note")