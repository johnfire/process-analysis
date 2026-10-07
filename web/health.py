"""Health of the running stack: database reachable, schema current, worker alive.

Each probe is isolated: one failing probe is reported, it does not stop the others from running.
The verdict itself is a pure function so it can be tested without any of the moving parts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine

from web.database import worker_heartbeats

UNKNOWN = "unknown: database unreachable"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthReport:
    is_healthy: bool
    checks: dict[str, str]


def summarise_health(
    is_database_reachable: bool,
    current_revision: str | None,
    head_revision: str | None,
    last_heartbeat: datetime | None,
    now: datetime,
    stale_after: timedelta,
) -> HealthReport:
    if not is_database_reachable:
        checks = {"database": "unreachable", "migrations": UNKNOWN, "worker": UNKNOWN}
        return HealthReport(is_healthy=False, checks=checks)
    checks = {
        "database": "ok",
        "migrations": migration_status(current_revision, head_revision),
        "worker": worker_status(last_heartbeat, now, stale_after),
    }
    return HealthReport(is_healthy=all(state == "ok" for state in checks.values()), checks=checks)


def migration_status(current_revision: str | None, head_revision: str | None) -> str:
    if head_revision is None:
        return "unknown head"
    if current_revision is None:
        return "not migrated"
    return "ok" if current_revision == head_revision else f"behind ({current_revision} != {head_revision})"


def worker_status(last_heartbeat: datetime | None, now: datetime, stale_after: timedelta) -> str:
    if last_heartbeat is None:
        return "never seen"
    age = now - last_heartbeat
    return "ok" if age <= stale_after else f"stale ({int(age.total_seconds())}s)"


def head_revision_of(migrations_dir: Path = MIGRATIONS_DIR) -> str | None:
    try:
        return ScriptDirectory(str(migrations_dir)).get_current_head()
    except Exception:
        log.exception("could not read migration head")
        return None


def probe_database(engine: Engine) -> tuple[bool, str | None, datetime | None]:
    """Reachability, applied revision and the freshest worker heartbeat, in one connection."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            current_revision = MigrationContext.configure(connection).get_current_revision()
            last_heartbeat = latest_heartbeat(connection) if current_revision else None
            return True, current_revision, last_heartbeat
    except Exception:
        log.exception("database probe failed")
        return False, None, None


def latest_heartbeat(connection) -> datetime | None:
    return connection.execute(select(func.max(worker_heartbeats.c.beat_at))).scalar()


def check_health(engine: Engine, head_revision: str | None, stale_after: timedelta) -> HealthReport:
    is_reachable, current_revision, last_heartbeat = probe_database(engine)
    return summarise_health(
        is_reachable, current_revision, head_revision, last_heartbeat, datetime.now(UTC), stale_after
    )
