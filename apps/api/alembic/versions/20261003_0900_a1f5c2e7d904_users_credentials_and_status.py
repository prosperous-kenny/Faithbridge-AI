"""Add credential and account-status columns to users.

Phase 1 needs to store a local-mode password and to disable accounts without
deleting them. password_hash is nullable on purpose: when AUTH_MODE=oidc the
identity provider owns the credential and this table must not hold one, so
externally-provisioned users simply have NULL here.

Revision ID: a1f5c2e7d904
Revises: 8e2b6d4f1a73
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1f5c2e7d904"
down_revision: str | None = "8e2b6d4f1a73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    # Destructive by necessity: downgrading discards stored credentials.
    op.drop_column("users", "is_active")
    op.drop_column("users", "password_hash")
