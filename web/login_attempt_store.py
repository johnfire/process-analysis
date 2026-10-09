"""Failed and successful login attempts, the input to the throttle."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import Connection

from web.database import login_attempts
from web.login_throttle import ATTEMPT_WINDOW

RETENTION_DAYS = 2


def record_attempt(
    connection: Connection, email_key: str, ip_address: str, is_success: bool, now: datetime
) -> None:
    connection.execute(
        insert(login_attempts).values(
            email_key=email_key, ip_address=ip_address, is_success=is_success, at=now
        )
    )


def count_recent_failures(
    connection: Connection, email_key: str, ip_address: str, now: datetime
) -> tuple[int, int]:
    """Failures in the window for this mailbox and for this address: (by_email, by_address)."""
    since = now - ATTEMPT_WINDOW

    def failures(column, value) -> int:
        return connection.execute(
            select(func.count())
            .select_from(login_attempts)
            .where(column == value)
            .where(login_attempts.c.at >= since)
            .where(login_attempts.c.is_success.is_(False))
        ).scalar_one()

    return failures(login_attempts.c.email_key, email_key), failures(login_attempts.c.ip_address, ip_address)


def clear_email_failures(connection: Connection, email_key: str, now: datetime) -> None:
    """A correct password clears that mailbox's failure count; the address count keeps running."""
    connection.execute(
        delete(login_attempts)
        .where(login_attempts.c.email_key == email_key)
        .where(login_attempts.c.is_success.is_(False))
        .where(login_attempts.c.at >= now - ATTEMPT_WINDOW)
    )


def prune_old_attempts(connection: Connection, now: datetime) -> None:
    connection.execute(
        delete(login_attempts).where(login_attempts.c.at < now - timedelta(days=RETENTION_DAYS))
    )
