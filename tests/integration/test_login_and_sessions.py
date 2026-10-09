"""Login, logout, throttling and request-forgery defence, through the real HTTP layer and Postgres."""

from __future__ import annotations

from sqlalchemy import text

from tests.integration.conftest import DEFAULT_PASSWORD, SITE, log_in, new_browser
from web import clock
from web.login_throttle import MAX_FAILURES_PER_EMAIL


def audit_actions(app) -> list[tuple[str, str]]:
    with app.state.engine.connect() as connection:
        return [
            (r.action, r.outcome)
            for r in connection.execute(text("SELECT action, outcome FROM audit_log ORDER BY id"))
        ]


def test_correct_login_sets_a_hardened_cookie_and_redirects(browser, make_user):
    make_user()
    response = log_in(browser)
    assert response.status_code == 303
    assert response.headers["location"] == "/clients"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie


def test_session_cookie_is_secure_when_configured(app, make_user):
    make_user()
    app.state.settings = type(app.state.settings)(**{**app.state.settings.__dict__, "is_cookie_secure": True})
    with new_browser(app) as client:
        assert "secure" in log_in(client).headers["set-cookie"].lower()


def test_only_a_hash_of_the_session_token_is_stored(browser, app, make_user):
    make_user()
    raw = log_in(browser).cookies["pa_session"]
    with app.state.engine.connect() as connection:
        stored = [r[0] for r in connection.execute(text("SELECT token_hash FROM sessions"))]
    assert raw not in stored and len(stored) == 1


def test_account_page_needs_a_session(browser):
    response = browser.get("/account")
    assert response.status_code == 303 and response.headers["location"] == "/login"


def test_wrong_password_and_unknown_email_look_identical(browser, make_user):
    make_user()
    wrong = log_in(browser, password="not the password at all")
    unknown = log_in(browser, email="nobody@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert "do not match" in wrong.text and "do not match" in unknown.text
    assert "pa_session" not in wrong.cookies


def test_failed_and_successful_logins_are_audited(browser, app, make_user):
    make_user()
    log_in(browser, password="not the password at all")
    log_in(browser)
    assert audit_actions(app) == [("login", "wrong_password"), ("login", "success")]


def test_repeated_failures_lock_the_mailbox_even_for_the_right_password(browser, make_user):
    make_user()
    for _ in range(MAX_FAILURES_PER_EMAIL):
        log_in(browser, password="not the password at all")
    assert log_in(browser).status_code == 429


def test_lockout_ends_after_the_window(browser, make_user, monkeypatch):
    make_user()
    for _ in range(MAX_FAILURES_PER_EMAIL):
        log_in(browser, password="not the password at all")
    later = clock.utcnow().replace(year=clock.utcnow().year + 1)
    monkeypatch.setattr(clock, "utcnow", lambda: later)
    assert log_in(browser).status_code == 303


def test_a_correct_login_clears_the_failure_count(browser, make_user):
    make_user()
    for _ in range(MAX_FAILURES_PER_EMAIL - 1):
        log_in(browser, password="not the password at all")
    assert log_in(browser).status_code == 303
    for _ in range(MAX_FAILURES_PER_EMAIL - 1):
        log_in(browser, password="not the password at all")
    assert log_in(browser).status_code == 303


def test_logout_ends_the_session_on_the_server(browser, app, make_user):
    make_user()
    token = log_in(browser).cookies["pa_session"]
    assert browser.post("/logout").status_code == 303
    stale = new_browser(app)
    stale.cookies.set("pa_session", token)
    assert stale.get("/account").status_code == 303


def test_expired_sessions_are_refused(browser, make_user, monkeypatch):
    make_user()
    log_in(browser)
    later = clock.utcnow().replace(year=clock.utcnow().year + 1)
    monkeypatch.setattr(clock, "utcnow", lambda: later)
    assert browser.get("/account").status_code == 303


def test_a_post_from_another_site_is_refused(browser, make_user):
    make_user()
    response = browser.post(
        "/login",
        data={"email": "chris@example.com", "password": DEFAULT_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403 and "pa_session" not in response.cookies


def test_a_post_with_no_origin_is_refused(app, make_user):
    make_user()
    from fastapi.testclient import TestClient

    bare = TestClient(app, base_url=SITE, follow_redirects=False)
    assert bare.post("/login", data={"email": "a@b.de", "password": "x"}).status_code == 403


def test_pages_carry_security_headers(browser):
    headers = browser.get("/login").headers
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"


def test_login_page_has_reset_link_and_invite_notice(browser):
    page = browser.get("/login").text
    assert 'href="/forgot"' in page and "invitation" in page.lower()


def test_landing_page_offers_login_when_anonymous_and_account_when_signed_in(browser, make_user):
    make_user()
    assert "data-open-login" in browser.get("/").text
    log_in(browser)
    page = browser.get("/").text
    assert 'href="/account"' in page and "data-open-login" not in page
