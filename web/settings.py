"""Runtime settings, read once from the environment.

Secrets never have defaults: a missing DATABASE_URL stops startup instead of quietly connecting
somewhere unintended.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    username: str
    password: str
    sender: str
    uses_starttls: bool


@dataclass(frozen=True)
class Settings:
    database_url: str
    worker_stale_after_seconds: int = 90
    log_level: str = "INFO"
    public_base_url: str = "https://process-analysis.christopherrehm.de"
    is_cookie_secure: bool = True
    mail: MailSettings | None = None


def mail_settings_from(source: Mapping[str, str]) -> MailSettings | None:
    """Mail is optional: without MAIL_HOST the app still works and shows invite links on screen."""
    host = source.get("MAIL_HOST", "").strip()
    if not host:
        return None
    return MailSettings(
        host=host,
        port=int(source.get("MAIL_PORT", "587")),
        username=source.get("MAIL_USERNAME", ""),
        password=source.get("MAIL_PASSWORD", ""),
        sender=source.get("MAIL_FROM", source.get("MAIL_USERNAME", "")),
        uses_starttls=source.get("MAIL_STARTTLS", "1") == "1",
    )


def settings_from_environment(environment: dict[str, str] | None = None) -> Settings:
    source = os.environ if environment is None else environment
    database_url = source.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return Settings(
        database_url=database_url,
        worker_stale_after_seconds=int(source.get("WORKER_STALE_AFTER_SECONDS", "90")),
        log_level=source.get("LOG_LEVEL", "INFO").upper(),
        public_base_url=source.get("PUBLIC_BASE_URL", Settings.public_base_url).rstrip("/"),
        is_cookie_secure=source.get("COOKIE_SECURE", "1") == "1",
        mail=mail_settings_from(source),
    )
