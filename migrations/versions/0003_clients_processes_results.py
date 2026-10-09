"""Clients, processes, transcripts, claims and results: what the viewer shows.

Written out in full rather than imported from web.database, so later edits to the live table
definitions cannot change what this migration does.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NEW_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
TIMESTAMP = sa.DateTime(timezone=True)


def process_reference() -> sa.Column:
    return sa.Column("process_id", sa.Uuid, sa.ForeignKey("processes.id", ondelete="CASCADE"), nullable=False)


def create_ownership_tables() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        sa.Column("owner_user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
    )
    op.create_table(
        "processes",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        sa.Column(
            "client_id", sa.Uuid, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column("slug", sa.String(200)),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.Text, nullable=False),
        sa.Column("organisation", postgresql.JSONB, nullable=False),
        sa.Column("cast", postgresql.JSONB, nullable=False),
        sa.Column("ground_truth", postgresql.JSONB),
        sa.Column("status", sa.String(20), nullable=False, server_default="analysed"),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.UniqueConstraint("client_id", "slug", name="uq_processes_client_slug"),
    )


def create_evidence_tables() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        process_reference(),
        sa.Column("person_key", sa.String(100), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.UniqueConstraint("process_id", "person_key", name="uq_transcripts_process_person"),
    )
    op.create_table(
        "claims",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        process_reference(),
        sa.Column("claim_set", sa.String(60), nullable=False),
        sa.Column("person_key", sa.String(100), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("body", postgresql.JSONB, nullable=False),
    )
    op.create_index(
        "ix_claims_process_set_person", "claims", ["process_id", "claim_set", "person_key", "position"]
    )
    op.create_table(
        "results",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        process_reference(),
        sa.Column("claim_set", sa.String(60), nullable=False),
        sa.Column("analyzer_version", sa.String(40), nullable=False),
        sa.Column("document", postgresql.JSONB, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "process_id", "claim_set", "analyzer_version", name="uq_results_process_set_version"
        ),
    )
    op.create_index("ix_results_process_id", "results", ["process_id"])


def upgrade() -> None:
    create_ownership_tables()
    create_evidence_tables()


def downgrade() -> None:
    for table in ("results", "claims", "transcripts", "processes", "clients"):
        op.drop_table(table)
