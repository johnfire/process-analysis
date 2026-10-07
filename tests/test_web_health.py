"""The health verdict is pure: every combination of database, schema and worker state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from web.health import migration_status, summarise_health, worker_status

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
STALE_AFTER = timedelta(seconds=90)


def healthy_report(**overrides):
    arguments = {
        "is_database_reachable": True,
        "current_revision": "0001",
        "head_revision": "0001",
        "last_heartbeat": NOW - timedelta(seconds=10),
        "now": NOW,
        "stale_after": STALE_AFTER,
    }
    arguments.update(overrides)
    return summarise_health(**arguments)


def test_all_good_is_healthy():
    report = healthy_report()
    assert report.is_healthy
    assert report.checks == {"database": "ok", "migrations": "ok", "worker": "ok"}


def test_unreachable_database_is_unhealthy():
    report = healthy_report(is_database_reachable=False, current_revision=None, last_heartbeat=None)
    assert not report.is_healthy
    assert report.checks == {
        "database": "unreachable",
        "migrations": "unknown: database unreachable",
        "worker": "unknown: database unreachable",
    }


def test_schema_behind_head_is_unhealthy():
    assert not healthy_report(current_revision="0001", head_revision="0002").is_healthy


def test_stale_worker_is_unhealthy():
    report = healthy_report(last_heartbeat=NOW - timedelta(seconds=91))
    assert not report.is_healthy
    assert report.checks["worker"] == "stale (91s)"


def test_migration_status_names_each_case():
    assert migration_status(None, "0001") == "not migrated"
    assert migration_status("0001", None) == "unknown head"
    assert migration_status("0001", "0001") == "ok"


def test_worker_never_seen_is_reported_as_such():
    assert worker_status(None, NOW, STALE_AFTER) == "never seen"


def test_heartbeat_exactly_at_threshold_still_counts():
    assert worker_status(NOW - STALE_AFTER, NOW, STALE_AFTER) == "ok"
