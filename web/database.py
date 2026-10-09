"""Database engine and the tables the web app reads directly.

Table definitions are SQLAlchemy Core, not ORM: the app issues a handful of explicit queries and
the schema itself is owned by the Alembic migrations in migrations/.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

metadata = MetaData()

NEW_UUID = text("gen_random_uuid()")
NOW = text("now()")
CASCADE = "CASCADE"

worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("worker_name", String(100), primary_key=True),
    Column("beat_at", DateTime(timezone=True), nullable=False),
)

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("email", String(320), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("is_admin", Boolean, nullable=False, server_default=text("false")),
    Column("totp_secret", String(64)),
    Column("is_totp_enabled", Boolean, nullable=False, server_default=text("false")),
    Column("totp_last_step", BigInteger),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("password_changed_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete=CASCADE), nullable=False, index=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("is_mfa_verified", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("ip_address", String(45)),
)

invites = Table(
    "invites",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("email", String(320), nullable=False),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("invited_by", Uuid, ForeignKey("users.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("accepted_at", DateTime(timezone=True)),
)

password_resets = Table(
    "password_resets",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete=CASCADE), nullable=False, index=True),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("used_at", DateTime(timezone=True)),
)

recovery_codes = Table(
    "recovery_codes",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete=CASCADE), nullable=False, index=True),
    Column("code_hash", String(64), nullable=False),
    Column("used_at", DateTime(timezone=True)),
)

# Deliberately no foreign key to users: the trail must outlive the account it describes.
audit_log = Table(
    "audit_log",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("actor_user_id", Uuid),
    Column("actor_label", String(320), nullable=False),
    Column("action", String(80), nullable=False),
    Column("target", String(320)),
    Column("outcome", String(40), nullable=False),
    Column("correlation_id", String(64)),
    Column("ip_address", String(45)),
)

login_attempts = Table(
    "login_attempts",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("email_key", String(320), nullable=False),
    Column("ip_address", String(45), nullable=False),
    Column("is_success", Boolean, nullable=False),
    Index("ix_login_attempts_email_at", "email_key", "at"),
    Index("ix_login_attempts_ip_at", "ip_address", "at"),
)


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
