"""Run the worker: `python -m worker`.

A failed heartbeat is logged and retried on the next tick; a transient database outage must not
kill the process, or /health would report a dead worker long after the database came back.
"""

from __future__ import annotations

import logging
import signal
import socket
import threading
from datetime import UTC, datetime

from web.database import create_database_engine
from web.settings import settings_from_environment
from web.structured_logging import configure_logging
from worker.heartbeat import record_heartbeat

HEARTBEAT_INTERVAL_SECONDS = 15

log = logging.getLogger("worker")


def run() -> None:
    settings = settings_from_environment()
    configure_logging(settings.log_level)
    engine = create_database_engine(settings.database_url)
    worker_name = socket.gethostname()
    stop_requested = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop_requested.set())
    signal.signal(signal.SIGINT, lambda *_: stop_requested.set())

    log.info("worker %s started", worker_name)
    while not stop_requested.is_set():
        try:
            record_heartbeat(engine, worker_name, datetime.now(UTC))
        except Exception:
            log.exception("heartbeat failed; retrying next tick")
        stop_requested.wait(HEARTBEAT_INTERVAL_SECONDS)
    log.info("worker %s stopped", worker_name)


if __name__ == "__main__":
    run()
