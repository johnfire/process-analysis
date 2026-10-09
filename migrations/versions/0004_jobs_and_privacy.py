"""Jobs for the worker, a sensitivity label per client, and private terms per process.

Written out in full, not imported from web.database.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NEW_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
TIMESTAMP = sa.DateTime(timezone=True)


def upgrade() -> None:
    # Existing clients default to the careful label; the invented corpus is not personal data.
    op.add_column(
        "clients", sa.Column("sensitivity", sa.String(20), nullable=False, server_default="sensitive")
    )
    op.execute("UPDATE clients SET sensitivity = 'standard' WHERE is_synthetic")
    op.add_column(
        "processes",
        sa.Column("private_terms", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        sa.Column(
            "process_id",
            sa.Uuid,
            sa.ForeignKey("processes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("claim_set", sa.String(60), nullable=False),
        sa.Column("max_tokens", sa.Integer, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("progress", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error", sa.Text),
        sa.Column("is_cancel_requested", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.Column("started_at", TIMESTAMP),
        sa.Column("finished_at", TIMESTAMP),
        sa.Column("heartbeat_at", TIMESTAMP),
    )
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_column("processes", "private_terms")
    op.drop_column("clients", "sensitivity")
