from __future__ import annotations

from web.login_throttle import MAX_FAILURES_PER_ADDRESS, MAX_FAILURES_PER_EMAIL, email_key, is_throttled


def test_below_both_limits_is_allowed():
    assert not is_throttled(MAX_FAILURES_PER_EMAIL - 1, MAX_FAILURES_PER_ADDRESS - 1)


def test_email_limit_throttles():
    assert is_throttled(MAX_FAILURES_PER_EMAIL, 0)


def test_address_limit_throttles():
    assert is_throttled(0, MAX_FAILURES_PER_ADDRESS)


def test_email_key_ignores_case_and_padding():
    assert email_key("  Chris@Example.COM ") == "chris@example.com"


def test_email_key_is_bounded():
    assert len(email_key("a" * 1000)) == 320
