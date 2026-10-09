"""The database is the last line of defence against replaying a one-time code under concurrency."""

from __future__ import annotations

from web.user_store import claim_totp_step, create_user


def test_a_time_step_can_be_claimed_only_once_and_never_backwards(engine):
    with engine.begin() as connection:
        user_id = create_user(connection, "a@example.com", "hash")
        assert claim_totp_step(connection, user_id, 100) is True
        assert claim_totp_step(connection, user_id, 100) is False
        assert claim_totp_step(connection, user_id, 99) is False
        assert claim_totp_step(connection, user_id, 101) is True


def test_a_used_recovery_code_cannot_be_spent_twice(engine):
    from datetime import UTC, datetime

    from web.recovery_code_store import replace_recovery_codes, use_recovery_code

    now = datetime.now(UTC)
    with engine.begin() as connection:
        user_id = create_user(connection, "a@example.com", "hash")
        replace_recovery_codes(connection, user_id, ["h1", "h2"])
        assert use_recovery_code(connection, user_id, "h1", now) is True
        assert use_recovery_code(connection, user_id, "h1", now) is False
        assert use_recovery_code(connection, user_id, "nope", now) is False


def test_duplicate_emails_are_rejected_case_insensitively(engine):
    with engine.begin() as connection:
        assert create_user(connection, "Chris@Example.com", "hash") is not None
        assert create_user(connection, "chris@example.com", "hash") is None
