"""Logging in and out: password, optional second factor, session cookie."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.engine import Connection, Row

from web import clock
from web.audit_trail import record_audit
from web.current_user import SignedInUser, client_address, load_session_user, require_user
from web.login_attempt_store import (
    clear_email_failures,
    count_recent_failures,
    prune_old_attempts,
    record_attempt,
)
from web.login_throttle import email_key, is_throttled
from web.one_time_tokens import hash_token, looks_like_recovery_code, new_token, normalise_recovery_code
from web.page_rendering import render_page
from web.passwords import (
    MAXIMUM_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    spend_verification_time,
    verify_password,
)
from web.recovery_code_store import use_recovery_code
from web.session_cookie import clear_session_cookie, read_session_token, set_session_cookie
from web.session_store import create_session, end_session, promote_to_full_session
from web.two_factor import accepted_step
from web.user_store import claim_totp_step, find_user_by_email, replace_password_hash

router = APIRouter()

WRONG_CREDENTIALS = "That email and password do not match."
WRONG_CODE = "That code did not work."
THROTTLED = "Too many attempts. Wait a few minutes and try again."
HOME_AFTER_LOGIN = "/clients"


def redirect(location: str) -> RedirectResponse:
    return RedirectResponse(location, status_code=303)


def login_failure(request: Request, template: str, message: str, status_code: int, **context) -> HTMLResponse:
    return render_page(request, template, status_code=status_code, error=message, **context)


def is_locked_out(connection: Connection, key: str, address: str) -> bool:
    by_email, by_address = count_recent_failures(connection, key, address, clock.utcnow())
    return is_throttled(by_email, by_address)


def password_matches(user: Row | None, password: str) -> bool:
    if user is None or len(password) > MAXIMUM_PASSWORD_LENGTH:
        spend_verification_time(password[:MAXIMUM_PASSWORD_LENGTH])
        return False
    return verify_password(user.password_hash, password)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if (user := load_session_user(request)) and user.is_mfa_verified:
        return redirect(HOME_AFTER_LOGIN)
    return render_page(request, "login.html")


@router.post("/login", response_class=HTMLResponse)
def log_in(request: Request, email: str = Form(""), password: str = Form("")):
    address, key, now = client_address(request), email_key(email), clock.utcnow()
    settings = request.app.state.settings
    with request.app.state.engine.begin() as connection:
        if is_locked_out(connection, key, address):
            record_audit(connection, None, key, "login", "throttled", address)
            return login_failure(request, "login.html", THROTTLED, 429, email=email)
        user = find_user_by_email(connection, key)
        is_correct = password_matches(user, password)
        record_attempt(connection, key, address, is_correct, now)
        prune_old_attempts(connection, now)
        if not is_correct or user is None:
            record_audit(connection, user.id if user else None, key, "login", "wrong_password", address)
            return login_failure(request, "login.html", WRONG_CREDENTIALS, 401, email=email)
        clear_email_failures(connection, key, now)
        if needs_rehash(user.password_hash):
            replace_password_hash(connection, user.id, hash_password(password))
        raw_token, hashed = new_token()
        create_session(connection, user.id, hashed, now, not user.is_totp_enabled, address)
        outcome = "awaiting_second_factor" if user.is_totp_enabled else "success"
        record_audit(connection, user.id, user.email, "login", outcome, address)
    response = redirect("/login/2fa" if user.is_totp_enabled else HOME_AFTER_LOGIN)
    set_session_cookie(response, raw_token, settings.is_cookie_secure)
    return response


@router.get("/login/2fa", response_class=HTMLResponse)
def second_factor_page(request: Request):
    user = load_session_user(request)
    if user is None:
        return redirect("/login")
    if user.is_mfa_verified:
        return redirect(HOME_AFTER_LOGIN)
    return render_page(request, "login_second_factor.html")


def second_factor_is_valid(connection: Connection, user: SignedInUser, typed: str) -> bool:
    """Accept an authenticator code or an unused recovery code; each works once."""
    now = clock.utcnow()
    if looks_like_recovery_code(typed):
        code_hash = hash_token(normalise_recovery_code(typed))
        return use_recovery_code(connection, user.user_id, code_hash, now)
    if user.totp_secret is None:
        return False
    step = accepted_step(user.totp_secret, typed, user.totp_last_step)
    return step is not None and claim_totp_step(connection, user.user_id, step)


@router.post("/login/2fa", response_class=HTMLResponse)
def verify_second_factor(request: Request, code: str = Form("")):
    user = load_session_user(request)
    if user is None:
        return redirect("/login")
    if user.is_mfa_verified:
        return redirect(HOME_AFTER_LOGIN)
    address, key, now = client_address(request), email_key(user.email), clock.utcnow()
    with request.app.state.engine.begin() as connection:
        if is_locked_out(connection, key, address):
            record_audit(connection, user.user_id, user.email, "login_second_factor", "throttled", address)
            return login_failure(request, "login_second_factor.html", THROTTLED, 429)
        is_valid = second_factor_is_valid(connection, user, code)
        record_attempt(connection, key, address, is_valid, now)
        outcome = "success" if is_valid else "wrong_code"
        record_audit(connection, user.user_id, user.email, "login_second_factor", outcome, address)
        if not is_valid:
            return login_failure(request, "login_second_factor.html", WRONG_CODE, 401)
        clear_email_failures(connection, key, now)
        promote_to_full_session(connection, user.session_id, now)
    return redirect(HOME_AFTER_LOGIN)


@router.post("/logout")
def log_out(request: Request, user: SignedInUser = Depends(require_user)):
    address = client_address(request)
    with request.app.state.engine.begin() as connection:
        end_session(connection, hash_token(read_session_token(request) or ""))
        record_audit(connection, user.user_id, user.email, "logout", "success", address)
    response = redirect("/?notice=signed_out")
    clear_session_cookie(response, request.app.state.settings.is_cookie_secure)
    return response
