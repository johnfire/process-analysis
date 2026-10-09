"""Getting in without a session: forgotten passwords and accepting an invitation."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.engine import Connection

from web import clock
from web.audit_trail import record_audit
from web.current_user import client_address
from web.link_token_store import (
    claim_invite,
    claim_reset,
    create_reset,
    find_open_invite,
    find_open_reset,
    has_recent_reset,
    void_open_resets,
)
from web.login_throttle import email_key
from web.mailer import reset_email, send_mail
from web.one_time_tokens import hash_token, new_token
from web.page_rendering import render_page
from web.passwords import hash_password, password_problem
from web.session_store import end_all_sessions
from web.user_store import change_password, create_user, find_user, find_user_by_email

router = APIRouter()

RESET_RESPONSE = "If that address has an account, we sent a link. It works once and expires in 30 minutes."
LINK_INVALID = "This link is invalid, already used, or expired."
PASSWORDS_DIFFER = "The two passwords do not match."
RESET_RESEND_COOLDOWN_SECONDS = 60


def redirect(location: str) -> RedirectResponse:
    return RedirectResponse(location, status_code=303)


def new_password_problem(password: str, confirmation: str, email: str) -> str | None:
    if password != confirmation:
        return PASSWORDS_DIFFER
    return password_problem(password, email)


@router.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return render_page(request, "forgot_password.html")


def issue_reset_link(request: Request, connection: Connection, email: str) -> tuple[str, str] | None:
    """Create a reset for a known address and return (email, raw_token); None when nothing to send."""
    now = clock.utcnow()
    user = find_user_by_email(connection, email)
    if user is None or has_recent_reset(connection, user.id, now, RESET_RESEND_COOLDOWN_SECONDS):
        return None
    void_open_resets(connection, user.id, now)
    raw_token, hashed = new_token()
    create_reset(connection, user.id, hashed, now)
    record_audit(
        connection, user.id, user.email, "password_reset_requested", "success", client_address(request)
    )
    return user.email, raw_token


@router.post("/forgot", response_class=HTMLResponse)
def request_reset(request: Request, background: BackgroundTasks, email: str = Form("")):
    """Always the same answer, whether or not the address has an account."""
    with request.app.state.engine.begin() as connection:
        issued = issue_reset_link(request, connection, email_key(email))
    if issued:
        subject, body = reset_email(request.app.state.settings.public_base_url, issued[1])
        background.add_task(send_mail, request.app.state.settings.mail, issued[0], subject, body)
    return render_page(request, "forgot_password.html", sent_message=RESET_RESPONSE)


@router.get("/reset/{token}", response_class=HTMLResponse)
def reset_page(request: Request, token: str):
    with request.app.state.engine.connect() as connection:
        is_open = find_open_reset(connection, hash_token(token), clock.utcnow()) is not None
    if not is_open:
        return render_page(request, "link_invalid.html", status_code=400, message=LINK_INVALID)
    return render_page(request, "reset_password.html", token=token)


@router.post("/reset/{token}", response_class=HTMLResponse)
def reset_password(request: Request, token: str, password: str = Form(""), confirmation: str = Form("")):
    now, address = clock.utcnow(), client_address(request)
    with request.app.state.engine.begin() as connection:
        reset = find_open_reset(connection, hash_token(token), now)
        if reset is None:
            return render_page(request, "link_invalid.html", status_code=400, message=LINK_INVALID)
        owner = find_user(connection, reset.user_id)
        email = owner.email if owner else ""
        problem = new_password_problem(password, confirmation, email)
        if problem:
            return render_page(request, "reset_password.html", status_code=400, token=token, error=problem)
        if not claim_reset(connection, reset.id, now):
            return render_page(request, "link_invalid.html", status_code=400, message=LINK_INVALID)
        change_password(connection, reset.user_id, hash_password(password), now)
        end_all_sessions(connection, reset.user_id)
        record_audit(connection, reset.user_id, email, "password_reset", "success", address)
    return redirect("/login?notice=password_reset")


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(request: Request, token: str):
    with request.app.state.engine.connect() as connection:
        invite = find_open_invite(connection, hash_token(token), clock.utcnow())
    if invite is None:
        return render_page(request, "link_invalid.html", status_code=400, message=LINK_INVALID)
    return render_page(request, "accept_invite.html", token=token, invited_email=invite.email)


@router.post("/invite/{token}", response_class=HTMLResponse)
def accept_invite(request: Request, token: str, password: str = Form(""), confirmation: str = Form("")):
    now, address = clock.utcnow(), client_address(request)
    with request.app.state.engine.begin() as connection:
        invite = find_open_invite(connection, hash_token(token), now)
        if invite is None:
            return render_page(request, "link_invalid.html", status_code=400, message=LINK_INVALID)
        problem = new_password_problem(password, confirmation, invite.email)
        if problem:
            context = {"token": token, "invited_email": invite.email, "error": problem}
            return render_page(request, "accept_invite.html", status_code=400, **context)
        if not claim_invite(connection, invite.id, now):
            return render_page(request, "link_invalid.html", status_code=400, message=LINK_INVALID)
        user_id = create_user(connection, invite.email, hash_password(password))
        outcome = "success" if user_id else "email_taken"
        record_audit(connection, user_id, invite.email, "invite_accepted", outcome, address)
        if user_id is None:
            return render_page(request, "link_invalid.html", status_code=400, message=LINK_INVALID)
    return redirect("/login?notice=invite_accepted")
