"""Database engine and the tables the web app reads directly.

Table definitions are SQLAlchemy Core, not ORM: the app issues a handful of explicit queries and
the schema itself is owned by the Alembic migrations in migrations/.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine
from sqlalchemy.engine import Engine

metadata = MetaData()

worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("worker_name", String(100), primary_key=True),
    Column("beat_at", DateTime(timezone=True), nullable=False),
)


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)
