"""The worker's two loops: proof of life for /health, and claiming jobs from the queue.

They run on separate threads on purpose. One transcript can take minutes inside a provider call;
if the heartbeat shared that thread, /health would report a dead worker during every long job and
the job itself would look abandoned. The heartbeat thread also touches the job being worked on, so
a job whose worker really died is the one that goes stale.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy.engine import Engine

from web import clock, job_store
from worker.extraction_job import run_extraction_job
from worker.heartbeat import record_heartbeat

log = logging.getLogger("worker")
HEARTBEAT_INTERVAL_SECONDS = 15
IDLE_POLL_SECONDS = 3


class CurrentJob:
    """The job this worker is running, shared with the heartbeat thread."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job_id = None

    def set(self, job_id) -> None:
        with self._lock:
            self._job_id = job_id

    def get(self):
        with self._lock:
            return self._job_id


def beat_once(engine: Engine, worker_name: str, current: CurrentJob, now: datetime) -> None:
    """One heartbeat. Each part is isolated so a failure in one cannot stop the other."""
    try:
        record_heartbeat(engine, worker_name, now)
    except Exception:
        log.exception("heartbeat failed; retrying next tick")
    job_id = current.get()
    if job_id is not None:
        try:
            with engine.begin() as connection:
                job_store.touch_job(connection, job_id, now)
        except Exception:
            log.exception("could not touch job %s", job_id)


def heartbeat_loop(engine: Engine, worker_name: str, current: CurrentJob, stop: threading.Event) -> None:
    while not stop.is_set():
        beat_once(engine, worker_name, current, clock.utcnow())
        stop.wait(HEARTBEAT_INTERVAL_SECONDS)


def work_once(engine: Engine, environment: Mapping[str, str], current: CurrentJob) -> bool:
    """Recover stale jobs, then run one queued job if there is one. True when a job was run."""
    with engine.begin() as connection:
        failed = job_store.fail_stale_jobs(connection, clock.utcnow())
        job = job_store.claim_next_job(connection, clock.utcnow())
    if failed:
        log.warning("failed %d job(s) whose worker stopped", failed)
    if job is None:
        return False
    current.set(job.id)
    try:
        run_extraction_job(engine, job, environment)
    finally:
        current.set(None)
    return True


def job_loop(
    engine: Engine, environment: Mapping[str, str], current: CurrentJob, stop: threading.Event
) -> None:
    while not stop.is_set():
        try:
            did_work = work_once(engine, environment, current)
        except Exception:
            log.exception("job loop iteration failed; continuing")
            did_work = False
        if not did_work:
            stop.wait(IDLE_POLL_SECONDS)
