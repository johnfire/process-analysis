"""Runtime settings, read once from the environment.

Secrets never have defaults: a missing DATABASE_URL stops startup instead of quietly connecting
somewhere unintended.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    worker_stale_after_seconds: int = 90
    log_level: str = "INFO"


def settings_from_environment(environment: dict[str, str] | None = None) -> Settings:
    source = os.environ if environment is None else environment
    database_url = source.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return Settings(
        database_url=database_url,
        worker_stale_after_seconds=int(source.get("WORKER_STALE_AFTER_SECONDS", "90")),
        log_level=source.get("LOG_LEVEL", "INFO").upper(),
    )
