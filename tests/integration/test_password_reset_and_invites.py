"""Getting in without a session: forgotten passwords and invitations."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from tests.integration.conftest import DEFAULT_PASSWORD, log_in, new_browser
from web import clock

NEW_PASSWORD = "copper meadow violin harbour"


@pytest.fixture
def sent_mail(monkeypatch):
    """Capture outgoing mail instead of connecting to an SMTP server."""
    outbox: list[tuple[str, str, str]] = []

    def capture(mail, recipient, subject, body):
        outbox.append((recipient, subject, body))
        return True

    monkeypatch.setattr("web.recovery_routes.send_mail", capture)
    monkeypatch.setattr("web.invite_routes.send_mail", capture)
    return outbox


def link_in(body: str, path: str) -> str:
    return re.search(rf"http://testserver({path}/\S+)", body).group(1)


# ---- password reset ----------------------------------------------------------------------------


def test_reset_answer_is_identical_for_known_and_unknown_addresses(browser, make_user, sent_mail):
    make_user()
    known = browser.post("/forgot", data={"email": "chris@example.com"})
    unknown = browser.post("/forgot", data={"email": "nobody@example.com"})
    assert known.status_code == unknown.status_code == 200
    assert known.text == unknown.text
    assert [m[0] for m in sent_mail] == ["chris@example.com"]


def test_reset_changes_the_password_and_the_link_works_once(browser, make_user, sent_mail):
    make_user()
    browser.post("/forgot", data={"email": "chris@example.com"})
    link = link_in(sent_mail[0][2], "/reset")
    assert browser.get(link).status_code == 200
    done = browser.post(link, data={"password": NEW_PASSWORD, "confirmation": NEW_PASSWORD})
    assert done.status_code == 303 and "notice=password_reset" in done.headers["location"]
    assert log_in(browser, password=NEW_PASSWORD).status_code == 303
    assert log_in(new_browser(browser.app), password=DEFAULT_PASSWORD).status_code == 401
    again = browser.post(
        link, data={"password": "another passphrase here", "confirmation": "another passphrase here"}
    )
    assert again.status_code == 400


def test_reset_link_expires_after_thirty_minutes(browser, make_user, sent_mail, monkeypatch):
    make_user()
    browser.post("/forgot", data={"email": "chris@example.com"})
    link = link_in(sent_mail[0][2], "/reset")
    from datetime import timedelta

    later = clock.utcnow() + timedelta(minutes=31)
    monkeypatch.setattr(clock, "utcnow", lambda: later)
    assert browser.get(link).status_code == 400


def test_a_new_reset_request_voids_the_older_link(browser, make_user, sent_mail, monkeypatch):
    make_user()
    browser.post("/forgot", data={"email": "chris@example.com"})
    first = link_in(sent_mail[0][2], "/reset")
    from datetime import timedelta

    later = clock.utcnow() + timedelta(minutes=5)
    monkeypatch.setattr(clock, "utcnow", lambda: later)
    browser.post("/forgot", data={"email": "chris@example.com"})
    assert browser.get(first).status_code == 400
    assert browser.get(link_in(sent_mail[1][2], "/reset")).status_code == 200


def test_reset_requests_are_rate_limited_per_account(browser, make_user, sent_mail):
    make_user()
    for _ in range(3):
        browser.post("/forgot", data={"email": "chris@example.com"})
    assert len(sent_mail) == 1


def test_reset_ends_every_existing_session(browser, app, make_user, sent_mail):
    make_user()
    log_in(browser)
    other = new_browser(app)
    log_in(other)
    browser.post("/forgot", data={"email": "chris@example.com"})
    link = link_in(sent_mail[0][2], "/reset")
    other.post(link, data={"password": NEW_PASSWORD, "confirmation": NEW_PASSWORD})
    assert browser.get("/account").status_code == 303


def test_reset_rejects_weak_or_mismatched_passwords_without_burning_the_link(browser, make_user, sent_mail):
    make_user()
    browser.post("/forgot", data={"email": "chris@example.com"})
    link = link_in(sent_mail[0][2], "/reset")
    assert browser.post(link, data={"password": "short", "confirmation": "short"}).status_code == 400
    assert (
        browser.post(link, data={"password": NEW_PASSWORD, "confirmation": "different one here"}).status_code
        == 400
    )
    assert (
        browser.post(link, data={"password": NEW_PASSWORD, "confirmation": NEW_PASSWORD}).status_code == 303
    )


def test_only_a_hash_of_the_reset_token_is_stored(browser, app, make_user, sent_mail):
    make_user()
    browser.post("/forgot", data={"email": "chris@example.com"})
    raw = link_in(sent_mail[0][2], "/reset").rsplit("/", 1)[1]
    with app.state.engine.connect() as connection:
        stored = [r[0] for r in connection.execute(text("SELECT token_hash FROM password_resets"))]
    assert raw not in stored and len(stored) == 1


# ---- invitations -------------------------------------------------------------------------------


def invite(browser, email="friend@example.com"):
    return browser.post("/invites", data={"email": email})


def test_admin_invites_and_the_invitee_sets_a_password(browser, app, make_user, sent_mail):
    make_user(is_admin=True)
    log_in(browser)
    assert invite(browser).status_code == 303
    link = link_in(sent_mail[0][2], "/invite")
    guest = new_browser(app)
    assert "friend@example.com" in guest.get(link).text
    done = guest.post(link, data={"password": NEW_PASSWORD, "confirmation": NEW_PASSWORD})
    assert done.status_code == 303
    assert log_in(guest, email="friend@example.com", password=NEW_PASSWORD).status_code == 303


def test_an_invited_user_is_not_an_administrator(browser, app, make_user, sent_mail):
    make_user(is_admin=True)
    log_in(browser)
    invite(browser)
    guest = new_browser(app)
    link = link_in(sent_mail[0][2], "/invite")
    guest.post(link, data={"password": NEW_PASSWORD, "confirmation": NEW_PASSWORD})
    log_in(guest, email="friend@example.com", password=NEW_PASSWORD)
    assert guest.get("/invites", headers={"Accept": "text/html"}).status_code == 403
    assert guest.post("/invites", data={"email": "third@example.com"}).status_code == 403


def test_an_invite_link_works_once(browser, app, make_user, sent_mail):
    make_user(is_admin=True)
    log_in(browser)
    invite(browser)
    link = link_in(sent_mail[0][2], "/invite")
    data = {"password": NEW_PASSWORD, "confirmation": NEW_PASSWORD}
    assert new_browser(app).post(link, data=data).status_code == 303
    assert new_browser(app).post(link, data=data).status_code == 400
    assert new_browser(app).get(link).status_code == 400


def test_invite_expires_after_seven_days(browser, app, make_user, sent_mail, monkeypatch):
    make_user(is_admin=True)
    log_in(browser)
    invite(browser)
    link = link_in(sent_mail[0][2], "/invite")
    from datetime import timedelta

    later = clock.utcnow() + timedelta(days=8)
    monkeypatch.setattr(clock, "utcnow", lambda: later)
    assert new_browser(app).get(link).status_code == 400


def test_inviting_an_existing_user_or_a_bad_address_is_refused(browser, make_user, sent_mail):
    make_user(is_admin=True)
    log_in(browser)
    assert invite(browser, "chris@example.com").status_code == 400
    assert invite(browser, "not-an-address").status_code == 400
    assert sent_mail == []


def test_the_link_is_shown_on_screen_when_mail_is_not_configured(browser, make_user):
    make_user(is_admin=True)
    log_in(browser)
    page = invite(browser)
    assert page.status_code == 200 and "/invite/" in page.text and "No mail was sent" in page.text


def test_anonymous_visitors_cannot_invite(browser):
    assert browser.post("/invites", data={"email": "x@example.com"}).status_code == 303
    assert browser.get("/invites").status_code == 303


def test_invite_accept_enforces_the_password_policy(browser, app, make_user, sent_mail):
    make_user(is_admin=True)
    log_in(browser)
    invite(browser)
    link = link_in(sent_mail[0][2], "/invite")
    assert new_browser(app).post(link, data={"password": "short", "confirmation": "short"}).status_code == 400


def test_invite_and_reset_actions_are_audited(browser, app, make_user, sent_mail):
    make_user(is_admin=True)
    log_in(browser)
    invite(browser)
    link = link_in(sent_mail[0][2], "/invite")
    new_browser(app).post(link, data={"password": NEW_PASSWORD, "confirmation": NEW_PASSWORD})
    with app.state.engine.connect() as connection:
        actions = [r[0] for r in connection.execute(text("SELECT action FROM audit_log"))]
    assert {"invite_sent", "invite_accepted"} <= set(actions)
