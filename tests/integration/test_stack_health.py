"""Migrations, the worker heartbeat and /health against a real Postgres."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.integration.conftest import alembic_config, table_names
from web.app import create_app
from web.database import worker_heartbeats
from web.settings import Settings
from worker.heartbeat import record_heartbeat


def test_migrations_create_and_remove_the_schema(engine, migrated_database_url):
    assert "worker_heartbeats" in table_names(engine)
    command.downgrade(alembic_config(migrated_database_url), "base")
    assert "worker_heartbeats" not in table_names(engine)
    command.upgrade(alembic_config(migrated_database_url), "head")


def test_heartbeat_upserts_one_row_per_worker(engine):
    first = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    record_heartbeat(engine, "worker-a", first)
    record_heartbeat(engine, "worker-a", first + timedelta(seconds=15))
    with engine.connect() as connection:
        rows = connection.execute(select(worker_heartbeats)).all()
    assert len(rows) == 1
    assert rows[0].beat_at == first + timedelta(seconds=15)


def test_health_is_green_once_migrated_and_worker_alive(engine, migrated_database_url):
    record_heartbeat(engine, "worker-a", datetime.now(UTC))
    client = TestClient(create_app(Settings(database_url=migrated_database_url)))
    response = client.get("/health")
    assert response.status_code == 200, response.json()
    expected_checks = {"database": "ok", "migrations": "ok", "worker": "ok"}
    assert response.json() == {"status": "ok", "checks": expected_checks}


def test_health_flags_a_worker_that_never_started(migrated_database_url):
    client = TestClient(create_app(Settings(database_url=migrated_database_url)))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["checks"]["worker"] == "never seen"
