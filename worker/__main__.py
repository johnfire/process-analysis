"""Run the worker: `python -m worker`.

A transient database outage is logged and retried on the next tick; it must not kill the process,
or /health would report a dead worker long after the database came back.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading

from web.database import create_database_engine
from web.settings import settings_from_environment
from web.structured_logging import configure_logging
from worker.job_loop import CurrentJob, heartbeat_loop, job_loop

log = logging.getLogger("worker")


def run() -> None:
    settings = settings_from_environment()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings.database_url)
    worker_name = socket.gethostname()
    stop_requested = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop_requested.set())
    signal.signal(signal.SIGINT, lambda *_: stop_requested.set())
    current = CurrentJob()

    log.info("worker %s started", worker_name)
    beating = threading.Thread(
        target=heartbeat_loop,
        args=(engine, worker_name, current, stop_requested),
        name="heartbeat",
        daemon=True,
    )
    beating.start()
    job_loop(engine, dict(os.environ), current, stop_requested)
    log.info("worker %s stopped", worker_name)


if __name__ == "__main__":
    run()
