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
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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

# Owned by a user, or by nobody: a client with no owner is shared with every signed-in user and
# read-only (the built-in synthetic corpus).
clients = Table(
    "clients",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("owner_user_id", Uuid, ForeignKey("users.id", ondelete=CASCADE), index=True),
    Column("name", String(200), nullable=False),
    Column("is_synthetic", Boolean, nullable=False, server_default=text("false")),
    Column("sensitivity", String(20), nullable=False, server_default="sensitive"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
)

processes = Table(
    "processes",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("client_id", Uuid, ForeignKey("clients.id", ondelete=CASCADE), nullable=False, index=True),
    Column("slug", String(200)),
    Column("name", String(200), nullable=False),
    Column("domain", Text, nullable=False),
    Column("organisation", JSONB, nullable=False),
    Column("cast", JSONB, nullable=False),
    Column("ground_truth", JSONB),
    Column("status", String(20), nullable=False, server_default="analysed"),
    Column("private_terms", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("client_id", "slug", name="uq_processes_client_slug"),
)

transcripts = Table(
    "transcripts",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("process_id", Uuid, ForeignKey("processes.id", ondelete=CASCADE), nullable=False),
    Column("person_key", String(100), nullable=False),
    Column("body", Text, nullable=False),
    UniqueConstraint("process_id", "person_key", name="uq_transcripts_process_person"),
)

claims = Table(
    "claims",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("process_id", Uuid, ForeignKey("processes.id", ondelete=CASCADE), nullable=False),
    Column("claim_set", String(60), nullable=False),
    Column("person_key", String(100), nullable=False),
    Column("position", Integer, nullable=False),
    Column("body", JSONB, nullable=False),
    Index("ix_claims_process_set_person", "process_id", "claim_set", "person_key", "position"),
)

# Append-only: a new analyzer version adds a row, it never overwrites an earlier result.
results = Table(
    "results",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("process_id", Uuid, ForeignKey("processes.id", ondelete=CASCADE), nullable=False, index=True),
    Column("claim_set", String(60), nullable=False),
    Column("analyzer_version", String(40), nullable=False),
    Column("document", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    UniqueConstraint("process_id", "claim_set", "analyzer_version", name="uq_results_process_set_version"),
)

# Long work, claimed by the worker one at a time. `progress` holds one entry per transcript.
jobs = Table(
    "jobs",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=NEW_UUID),
    Column("process_id", Uuid, ForeignKey("processes.id", ondelete=CASCADE), nullable=False, index=True),
    Column("created_by", Uuid, ForeignKey("users.id", ondelete="SET NULL")),
    Column("status", String(30), nullable=False),
    Column("provider", String(40), nullable=False),
    Column("model", String(120), nullable=False),
    Column("claim_set", String(60), nullable=False),
    Column("max_tokens", Integer, nullable=False),
    Column("tokens_in", Integer, nullable=False, server_default=text("0")),
    Column("tokens_out", Integer, nullable=False, server_default=text("0")),
    Column("progress", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("error", Text),
    Column("is_cancel_requested", Boolean, nullable=False, server_default=text("false")),
    Column("correlation_id", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=NOW),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("heartbeat_at", DateTime(timezone=True)),
    Index("ix_jobs_status_created", "status", "created_at"),
)


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
