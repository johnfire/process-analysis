"""When to refuse a login attempt. The decision is pure; the counts come from the database."""

from __future__ import annotations

from datetime import timedelta

ATTEMPT_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_ADDRESS = 20  # higher: an office or a mobile carrier shares one address


def is_throttled(failures_for_email: int, failures_for_address: int) -> bool:
    return failures_for_email >= MAX_FAILURES_PER_EMAIL or failures_for_address >= MAX_FAILURES_PER_ADDRESS


def email_key(email: str) -> str:
    """One bucket per mailbox however it is capitalised or padded."""
    return email.strip().lower()[:320]
