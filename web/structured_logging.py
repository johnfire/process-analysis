"""JSON-lines logging that carries the current correlation ID on every record.

The ID lives in a context variable, so anything logged while serving a request, or while a
worker processes a job, is traceable back to the unit of work that caused it.
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from datetime import UTC, datetime

correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "at": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": correlation_id.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLineFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
