"""The job queue: enqueue, claim, report progress, finish, cancel, and recover from a dead worker.

Postgres is the queue. A job is claimed with SELECT ... FOR UPDATE SKIP LOCKED, so two workers can
never take the same one, and a job whose heartbeat stops is failed rather than left "running"
forever.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection, Row

from web.database import clients, jobs, processes
from web.process_store import is_visible_to

QUEUED = "queued"
RUNNING = "running"
FINISHED_STATES = frozenset({"done", "partial", "failed", "cancelled", "stopped_cost_cap"})
ACTIVE_STATES = (QUEUED, RUNNING)
STALE_AFTER = timedelta(seconds=90)
WORKER_LOST = "The worker stopped while this job was running; finished transcripts were kept."


def enqueue_job(
    connection: Connection,
    process_id: UUID,
    created_by: UUID,
    provider: str,
    model: str,
    claim_set: str,
    max_tokens: int,
    correlation_id: str,
) -> UUID:
    return connection.execute(
        insert(jobs)
        .values(
            process_id=process_id,
            created_by=created_by,
            status=QUEUED,
            provider=provider,
            model=model,
            claim_set=claim_set,
            max_tokens=max_tokens,
            correlation_id=correlation_id,
        )
        .returning(jobs.c.id)
    ).scalar_one()


def has_active_job(connection: Connection, process_id: UUID) -> bool:
    return (
        connection.execute(
            select(jobs.c.id)
            .where(jobs.c.process_id == process_id)
            .where(jobs.c.status.in_(ACTIVE_STATES))
            .limit(1)
        ).first()
        is not None
    )


def claim_next_job(connection: Connection, now: datetime) -> Row | None:
    """Take the oldest queued job for this worker, or None. Safe against concurrent workers."""
    row = connection.execute(
        select(jobs)
        .where(jobs.c.status == QUEUED)
        .order_by(jobs.c.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if row is None:
        return None
    connection.execute(
        update(jobs).where(jobs.c.id == row.id).values(status=RUNNING, started_at=now, heartbeat_at=now)
    )
    return row


def touch_job(connection: Connection, job_id: UUID, now: datetime) -> None:
    connection.execute(
        update(jobs).where(jobs.c.id == job_id).where(jobs.c.status == RUNNING).values(heartbeat_at=now)
    )


def record_progress(
    connection: Connection,
    job_id: UUID,
    progress: list[dict[str, Any]],
    tokens_in: int,
    tokens_out: int,
    now: datetime,
) -> None:
    connection.execute(
        update(jobs)
        .where(jobs.c.id == job_id)
        .values(progress=progress, tokens_in=tokens_in, tokens_out=tokens_out, heartbeat_at=now)
    )


def finish_job(connection: Connection, job_id: UUID, status: str, error: str | None, now: datetime) -> None:
    connection.execute(
        update(jobs).where(jobs.c.id == job_id).values(status=status, error=error, finished_at=now)
    )


def job_state(connection: Connection, job_id: UUID) -> tuple[bool, bool]:
    """(still exists, cancel requested). A job whose process was deleted no longer exists."""
    row = connection.execute(select(jobs.c.is_cancel_requested).where(jobs.c.id == job_id)).first()
    return (row is not None, bool(row and row.is_cancel_requested))


def fail_stale_jobs(connection: Connection, now: datetime) -> int:
    """Fail running jobs whose worker stopped reporting. Returns how many were failed."""
    stale = connection.execute(
        update(jobs)
        .where(jobs.c.status == RUNNING)
        .where(jobs.c.heartbeat_at < now - STALE_AFTER)
        .values(status="failed", error=WORKER_LOST, finished_at=now)
        .returning(jobs.c.process_id)
    ).all()
    for row in stale:
        connection.execute(
            update(processes)
            .where(processes.c.id == row.process_id)
            .where(processes.c.status == "extracting")
            .values(status="failed")
        )
    return len(stale)


def find_visible_job(connection: Connection, job_id: UUID, user_id: UUID) -> Row | None:
    return connection.execute(
        select(
            jobs,
            processes.c.name.label("process_name"),
            processes.c.id.label("owning_process_id"),
            clients.c.owner_user_id.label("client_owner"),
        )
        .join_from(jobs, processes, jobs.c.process_id == processes.c.id)
        .join(clients, processes.c.client_id == clients.c.id)
        .where(jobs.c.id == job_id)
        .where(is_visible_to(user_id))
    ).first()


def request_cancel(connection: Connection, job_id: UUID) -> None:
    connection.execute(
        update(jobs)
        .where(jobs.c.id == job_id)
        .where(jobs.c.status.in_(ACTIVE_STATES))
        .values(is_cancel_requested=True)
    )


def list_jobs(connection: Connection, process_id: UUID) -> list[Row]:
    return list(
        connection.execute(
            select(jobs).where(jobs.c.process_id == process_id).order_by(jobs.c.created_at.desc())
        )
    )
