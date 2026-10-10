from __future__ import annotations

import pytest

from web import manage
from web.email_addresses import is_plausible_email


@pytest.mark.parametrize("address", ["chris@example.com", "a.b+tag@sub.example.de", "x@y.io"])
def test_ordinary_addresses_are_accepted(address):
    assert is_plausible_email(address)


@pytest.mark.parametrize(
    "address",
    [
        "YOUR-REAL-EMAIL",
        "you@example",
        "@example.com",
        "chris@",
        "a@@b.com",
        "a b@c.com",
        "a@b..com",
        "a@.com",
        "a@b.",
        "",
        "x" * 320 + "@a.de",
    ],
)
def test_placeholders_and_typos_are_refused(address):
    assert not is_plausible_email(address)


def test_create_user_refuses_a_placeholder_before_asking_for_any_password(monkeypatch):
    def fail_if_asked(*args, **kwargs):
        raise AssertionError("the password prompt must not appear for an invalid address")

    monkeypatch.setattr(manage.getpass, "getpass", fail_if_asked)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="not an email address"):
        manage.create_administrator("YOUR-REAL-EMAIL", is_admin=True)
