"""Phase 6: payment provider references, richer placements, WhatsApp messages.

* ``donations.provider_reference`` — the provider-side transaction id captured
  when a pledge is paid, kept so reconciliation and the audit trail can tie the
  ledger to the payment provider (PRD §14).
* ``placements.skills|status|mentor_user_id`` — job/skill matching and
  mentorship for the Employment Empowerment Module (PRD §14).
* ``sent_messages`` — an append-only record of outbound WhatsApp messages
  (channel adapters behind a provider interface, mock by default).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

revision = "a9b1c2d3e4f5"
down_revision = "f6c3a8d1b2e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "donations",
        sa.Column("provider_reference", sa.String(128), nullable=True),
    )

    op.add_column(
        "placements",
        sa.Column(
            "skills",
            postgresql.ARRAY(sa.String(50)),
            nullable=False,
            server_default=text("'{}'"),
        ),
    )
    op.add_column(
        "placements",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=text("'placed'"),
        ),
    )
    op.add_column(
        "placements",
        sa.Column("mentor_user_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_placements_mentor_user_id_users",
        "placements",
        "users",
        ["mentor_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_placements_mentor_user_id", "placements", ["mentor_user_id"]
    )

    op.create_table(
        "sent_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("recipient_phone", sa.String(30), nullable=False),
        sa.Column("template", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=text("'queued'"),
        ),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_sent_messages_organization_id", "sent_messages", ["organization_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_sent_messages_organization_id", table_name="sent_messages")
    op.drop_table("sent_messages")

    op.drop_index("ix_placements_mentor_user_id", table_name="placements")
    op.drop_constraint(
        "fk_placements_mentor_user_id_users", "placements", type_="foreignkey"
    )
    op.drop_column("placements", "mentor_user_id")
    op.drop_column("placements", "status")
    op.drop_column("placements", "skills")

    op.drop_column("donations", "provider_reference")