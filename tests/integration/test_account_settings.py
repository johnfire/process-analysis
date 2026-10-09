"""The settings page: password change, data export, and the two-step account deletion."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.integration.conftest import DEFAULT_PASSWORD, log_in, new_browser

NEW_PASSWORD = "copper meadow violin harbour"
USER_TABLES = ("users", "sessions", "invites", "password_resets", "recovery_codes")


def count_rows(app, table: str) -> int:
    with app.state.engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()


def change_password(browser, current=DEFAULT_PASSWORD, new=NEW_PASSWORD, confirmation=None):
    data = {"current_password": current, "new_password": new, "confirmation": confirmation or new}
    return browser.post("/account/password", data=data)


def test_changing_the_password_signs_out_other_devices_but_not_this_one(browser, app, make_user):
    make_user()
    log_in(browser)
    phone = new_browser(app)
    log_in(phone)
    assert change_password(browser).status_code == 303
    assert browser.get("/account").status_code == 200
    assert phone.get("/account").status_code == 303


def test_the_new_password_works_and_the_old_one_does_not(browser, app, make_user):
    make_user()
    log_in(browser)
    change_password(browser)
    assert log_in(new_browser(app), password=NEW_PASSWORD).status_code == 303
    assert log_in(new_browser(app), password=DEFAULT_PASSWORD).status_code == 401


@pytest.mark.parametrize(
    ("current", "new", "confirmation"),
    [
        ("wrong current password", NEW_PASSWORD, NEW_PASSWORD),
        (DEFAULT_PASSWORD, NEW_PASSWORD, "something else entirely"),
        (DEFAULT_PASSWORD, "short", "short"),
    ],
)
def test_bad_password_changes_are_refused_and_change_nothing(
    browser, app, make_user, current, new, confirmation
):
    make_user()
    log_in(browser)
    assert change_password(browser, current, new, confirmation).status_code == 400
    assert log_in(new_browser(app)).status_code == 303


def test_export_contains_the_users_data_and_no_secrets(browser, make_user):
    make_user()
    log_in(browser)
    response = browser.get("/account/export")
    document = json.loads(response.text)
    assert "attachment" in response.headers["content-disposition"]
    assert document["profile"]["email"] == "chris@example.com"
    assert any(entry["action"] == "login" for entry in document["audit_log"])
    for secret_name in ("password_hash", "totp_secret", "token_hash", "argon2"):
        assert secret_name not in response.text


def test_visiting_the_delete_page_deletes_nothing(browser, app, make_user):
    make_user()
    log_in(browser)
    page = browser.get("/account/delete")
    assert page.status_code == 200 and "DELETE" in page.text
    assert count_rows(app, "users") == 1


@pytest.mark.parametrize(
    ("password", "confirmation"),
    [("wrong password here", "DELETE"), (DEFAULT_PASSWORD, "delete"), (DEFAULT_PASSWORD, "")],
)
def test_deletion_needs_both_the_password_and_the_typed_word(browser, app, make_user, password, confirmation):
    make_user()
    log_in(browser)
    response = browser.post("/account/delete", data={"password": password, "confirmation": confirmation})
    assert response.status_code == 400
    assert count_rows(app, "users") == 1


def test_deletion_removes_every_row_belonging_to_the_user(browser, app, make_user):
    make_user(is_admin=True)
    log_in(browser)
    browser.post("/invites", data={"email": "friend@example.com"})
    browser.post("/forgot", data={"email": "chris@example.com"})
    browser.post("/account/2fa/start")
    done = browser.post("/account/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"})
    assert done.status_code == 303 and "account_deleted" in done.headers["location"]
    for table in ("users", "sessions", "password_resets", "recovery_codes"):
        assert count_rows(app, table) == 0, table


def test_deletion_blanks_the_identity_in_the_audit_trail_but_keeps_the_events(browser, app, make_user):
    make_user()
    log_in(browser)
    browser.post("/account/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"})
    with app.state.engine.connect() as connection:
        rows = connection.execute(text("SELECT actor_label, action, ip_address FROM audit_log")).all()
    assert rows and all(row.actor_label == "deleted-account" for row in rows)
    assert {"login", "account_delete"} <= {row.action for row in rows}
    assert all(row.ip_address is None for row in rows)


def test_after_deletion_the_session_and_login_are_dead(browser, app, make_user):
    make_user()
    log_in(browser)
    browser.post("/account/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"})
    assert browser.get("/account").status_code == 303
    assert log_in(new_browser(app)).status_code == 401


def test_settings_pages_need_a_session(browser):
    for path in ("/account", "/account/export", "/account/delete"):
        assert browser.get(path).status_code == 303, path
    for path in ("/account/password", "/account/delete", "/account/2fa/start", "/logout"):
        assert browser.post(path, data={}).status_code == 303, path
