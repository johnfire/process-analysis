"""Accounts: users, sessions, invites, password resets, recovery codes, audit log, login attempts.

The schema is written out here rather than imported from web.database, so a later edit to the
live table definitions cannot change what this migration does.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NEW_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
TIMESTAMP = sa.DateTime(timezone=True)


def user_reference() -> sa.Column:
    return sa.Column(
        "user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


def create_identity_tables() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("totp_secret", sa.String(64)),
        sa.Column("is_totp_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("totp_last_step", sa.BigInteger),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.Column("password_changed_at", TIMESTAMP, nullable=False, server_default=NOW),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        user_reference(),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("is_mfa_verified", sa.Boolean, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("ip_address", sa.String(45)),
    )


def create_token_tables() -> None:
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", sa.Uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("accepted_at", TIMESTAMP),
    )
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        user_reference(),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.Column("used_at", TIMESTAMP),
    )
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=NEW_UUID),
        user_reference(),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", TIMESTAMP),
    )


def create_trail_tables() -> None:
    # No foreign key from audit_log to users: the trail must outlive the account it describes.
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.Column("actor_user_id", sa.Uuid),
        sa.Column("actor_label", sa.String(320), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target", sa.String(320)),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("ip_address", sa.String(45)),
    )
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("at", TIMESTAMP, nullable=False, server_default=NOW),
        sa.Column("email_key", sa.String(320), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("is_success", sa.Boolean, nullable=False),
    )
    op.create_index("ix_login_attempts_email_at", "login_attempts", ["email_key", "at"])
    op.create_index("ix_login_attempts_ip_at", "login_attempts", ["ip_address", "at"])


def upgrade() -> None:
    create_identity_tables()
    create_token_tables()
    create_trail_tables()


def downgrade() -> None:
    for table in (
        "login_attempts",
        "audit_log",
        "recovery_codes",
        "password_resets",
        "invites",
        "sessions",
        "users",
    ):
        op.drop_table(table)
