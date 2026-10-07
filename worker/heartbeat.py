"""The worker's proof of life, read by /health."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine

from web.database import worker_heartbeats


def record_heartbeat(engine: Engine, worker_name: str, beat_at: datetime) -> None:
    statement = insert(worker_heartbeats).values(worker_name=worker_name, beat_at=beat_at)
    upsert = statement.on_conflict_do_update(
        index_elements=[worker_heartbeats.c.worker_name], set_={"beat_at": beat_at}
    )
    with engine.begin() as connection:
        connection.execute(upsert)
