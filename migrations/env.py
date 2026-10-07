"""Alembic environment: online migrations only, URL from DATABASE_URL."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine

from web.database import metadata


def run_migrations_online() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run migrations")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
