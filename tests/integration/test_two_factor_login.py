"""Opt-in two-factor authentication: setup, login with a code, recovery codes, turning it off."""

from __future__ import annotations

import re

import pyotp
from sqlalchemy import text

from tests.integration.conftest import DEFAULT_PASSWORD, log_in, new_browser
from web.two_factor import STEP_SECONDS


def stored_secret(app) -> str:
    with app.state.engine.connect() as connection:
        return connection.execute(text("SELECT totp_secret FROM users")).scalar_one()


def enable_two_factor(browser, app) -> list[str]:
    """Run setup through the real pages and return the recovery codes shown once."""
    browser.post("/account/2fa/start")
    secret = stored_secret(app)
    page = browser.post("/account/2fa/enable", data={"code": pyotp.TOTP(secret).now()})
    assert page.status_code == 200, page.text
    return re.findall(r"<code>([a-z2-9]{5}-[a-z2-9]{5})</code>", page.text)


def next_step_code(secret: str) -> str:
    """The code for the next 30-second step: valid within drift, and never the one just used."""
    import time

    return pyotp.TOTP(secret).at(time.time() + STEP_SECONDS)


def test_setup_shows_a_qr_code_and_the_key(browser, app, make_user):
    make_user()
    log_in(browser)
    page = browser.post("/account/2fa/start").text
    assert "<svg" in page and stored_secret(app) in page


def test_a_wrong_code_during_setup_leaves_two_factor_off(browser, app, make_user):
    make_user()
    log_in(browser)
    browser.post("/account/2fa/start")
    secret = stored_secret(app)
    wrong = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"
    assert browser.post("/account/2fa/enable", data={"code": wrong}).status_code == 400
    with app.state.engine.connect() as connection:
        assert connection.execute(text("SELECT is_totp_enabled FROM users")).scalar_one() is False


def test_setup_issues_eight_one_time_recovery_codes(browser, app, make_user):
    make_user()
    log_in(browser)
    codes = enable_two_factor(browser, app)
    assert len(codes) == 8 == len(set(codes))
    with app.state.engine.connect() as connection:
        stored = [r[0] for r in connection.execute(text("SELECT code_hash FROM recovery_codes"))]
    assert not set(codes) & set(stored)


def test_with_two_factor_on_a_password_alone_gets_no_access(browser, app, make_user):
    make_user()
    log_in(browser)
    enable_two_factor(browser, app)
    other = new_browser(app)
    response = log_in(other)
    assert response.status_code == 303 and response.headers["location"] == "/login/2fa"
    assert other.get("/account").status_code == 303
    assert other.get("/account/export").status_code == 303


def test_a_valid_code_completes_the_login(browser, app, make_user):
    make_user()
    log_in(browser)
    enable_two_factor(browser, app)
    other = new_browser(app)
    log_in(other)
    done = other.post("/login/2fa", data={"code": next_step_code(stored_secret(app))})
    assert done.status_code == 303 and done.headers["location"] == "/account"
    assert other.get("/account").status_code == 200


def test_a_wrong_code_is_refused_and_audited(browser, app, make_user):
    make_user()
    log_in(browser)
    enable_two_factor(browser, app)
    other = new_browser(app)
    log_in(other)
    assert other.post("/login/2fa", data={"code": "abcdef"}).status_code == 401
    assert other.get("/account").status_code == 303
    with app.state.engine.connect() as connection:
        outcomes = [
            r[0]
            for r in connection.execute(
                text("SELECT outcome FROM audit_log WHERE action = 'login_second_factor'")
            )
        ]
    assert outcomes == ["wrong_code"]


def test_a_code_that_was_already_used_cannot_be_replayed(browser, app, make_user):
    make_user()
    log_in(browser)
    enable_two_factor(browser, app)
    secret = stored_secret(app)
    code = next_step_code(secret)
    first = new_browser(app)
    log_in(first)
    assert first.post("/login/2fa", data={"code": code}).status_code == 303
    second = new_browser(app)
    log_in(second)
    assert second.post("/login/2fa", data={"code": code}).status_code == 401


def test_a_recovery_code_works_once(browser, app, make_user):
    make_user()
    log_in(browser)
    codes = enable_two_factor(browser, app)
    first = new_browser(app)
    log_in(first)
    assert first.post("/login/2fa", data={"code": codes[0]}).status_code == 303
    second = new_browser(app)
    log_in(second)
    assert second.post("/login/2fa", data={"code": codes[0]}).status_code == 401
    assert second.post("/login/2fa", data={"code": codes[1].upper()}).status_code == 303


def test_repeated_wrong_codes_trigger_the_lockout(browser, app, make_user):
    make_user()
    log_in(browser)
    enable_two_factor(browser, app)
    other = new_browser(app)
    log_in(other)
    statuses = [other.post("/login/2fa", data={"code": "abcdef"}).status_code for _ in range(7)]
    assert statuses[-1] == 429


def test_turning_it_off_needs_the_password_and_removes_the_secret_and_codes(browser, app, make_user):
    make_user()
    log_in(browser)
    enable_two_factor(browser, app)
    assert browser.post("/account/2fa/disable", data={"password": "wrong password here"}).status_code == 400
    assert browser.post("/account/2fa/disable", data={"password": DEFAULT_PASSWORD}).status_code == 303
    with app.state.engine.connect() as connection:
        row = connection.execute(text("SELECT totp_secret, is_totp_enabled FROM users")).one()
        assert tuple(row) == (None, False)
        assert connection.execute(text("SELECT count(*) FROM recovery_codes")).scalar_one() == 0
    assert log_in(new_browser(app)).headers["location"] == "/account"


def test_new_recovery_codes_replace_the_old_ones(browser, app, make_user):
    make_user()
    log_in(browser)
    old = enable_two_factor(browser, app)
    page = browser.post("/account/2fa/recovery-codes", data={"password": DEFAULT_PASSWORD})
    new = re.findall(r"<code>([a-z2-9]{5}-[a-z2-9]{5})</code>", page.text)
    assert len(new) == 8 and not set(new) & set(old)
    other = new_browser(app)
    log_in(other)
    assert other.post("/login/2fa", data={"code": old[0]}).status_code == 401


def test_regenerating_codes_needs_the_password(browser, app, make_user):
    make_user()
    log_in(browser)
    enable_two_factor(browser, app)
    assert (
        browser.post("/account/2fa/recovery-codes", data={"password": "nope nope nope nope"}).status_code
        == 400
    )
