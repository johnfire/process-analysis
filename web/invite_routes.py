"""Administrators invite new users. Signup is invite-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.engine import Connection

from web import clock
from web.audit_trail import record_audit
from web.current_user import SignedInUser, client_address, require_admin
from web.email_addresses import is_plausible_email
from web.link_token_store import create_invite, list_invites
from web.login_throttle import email_key
from web.mailer import invite_email, send_mail
from web.one_time_tokens import new_token
from web.page_rendering import render_page
from web.user_store import find_user_by_email

router = APIRouter(prefix="/invites")

INVALID_EMAIL = "Enter a valid email address."
ALREADY_REGISTERED = "That address already has an account."


@router.get("", response_class=HTMLResponse)
def invites_page(request: Request, user: SignedInUser = Depends(require_admin)):
    with request.app.state.engine.connect() as connection:
        return invites_listing(request, connection, user)


def invite_problem(connection: Connection, invited: str) -> str | None:
    if not is_plausible_email(invited):
        return INVALID_EMAIL
    return ALREADY_REGISTERED if find_user_by_email(connection, invited) else None


def invites_listing(request: Request, connection: Connection, user: SignedInUser, **context):
    return render_page(
        request, "invites.html", user=user, invites=list_invites(connection), now=clock.utcnow(), **context
    )


@router.post("", response_class=HTMLResponse)
def send_invite(
    request: Request,
    email: str = Form(""),
    user: SignedInUser = Depends(require_admin),
):
    address, invited = client_address(request), email_key(email)
    settings = request.app.state.settings
    with request.app.state.engine.begin() as connection:
        problem = invite_problem(connection, invited)
        if problem:
            return invites_listing(request, connection, user, status_code=400, error=problem)
        raw_token, hashed = new_token()
        create_invite(connection, invited, hashed, user.user_id, clock.utcnow())
        record_audit(connection, user.user_id, user.email, "invite_sent", "success", address, invited)
    subject, body = invite_email(settings.public_base_url, raw_token)
    if send_mail(settings.mail, invited, subject, body):
        return RedirectResponse("/invites?notice=invite_sent", status_code=303)
    # Mail is off or failed: show the link once so the inviter can hand it over themselves.
    link = f"{settings.public_base_url}/invite/{raw_token}"
    with request.app.state.engine.connect() as connection:
        return invites_listing(request, connection, user, manual_link=link, manual_link_email=invited)
