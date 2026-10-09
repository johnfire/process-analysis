"""The signed-in user's own account: password, two-factor, data export, deletion."""

from __future__ import annotations

import json
from dataclasses import replace

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.engine import Connection

from web import clock
from web.audit_trail import erase_identity, export_audit_entries, record_audit
from web.current_user import SignedInUser, client_address, require_user
from web.link_token_store import list_invites
from web.one_time_tokens import hash_token, new_recovery_codes
from web.page_rendering import render_page
from web.passwords import hash_password, password_problem, verify_password
from web.recovery_code_store import count_unused_codes, delete_recovery_codes, replace_recovery_codes
from web.session_cookie import clear_session_cookie
from web.session_store import end_all_sessions
from web.two_factor import accepted_step, new_secret, provisioning_uri, qr_code_svg
from web.user_store import (
    change_password,
    delete_user,
    disable_totp,
    enable_totp,
    export_profile,
    find_user,
    store_pending_totp_secret,
)

router = APIRouter(prefix="/account")

WRONG_PASSWORD = "The current password is not correct."
PASSWORDS_DIFFER = "The two new passwords do not match."
WRONG_CODE = "That code did not work. Check the time on your phone and try the next code."
DELETE_PHRASE = "DELETE"


def redirect(location: str) -> RedirectResponse:
    return RedirectResponse(location, status_code=303)


def settings_page(
    request: Request, connection: Connection, user: SignedInUser, status_code: int = 200, **context
):
    unused = count_unused_codes(connection, user.user_id) if user.is_totp_enabled else 0
    return render_page(
        request, "account.html", user=user, status_code=status_code, unused_codes=unused, **context
    )


@router.get("", response_class=HTMLResponse)
def account_page(request: Request, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        return settings_page(request, connection, user)


@router.post("/password", response_class=HTMLResponse)
def change_own_password(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirmation: str = Form(""),
    user: SignedInUser = Depends(require_user),
):
    now, address = clock.utcnow(), client_address(request)
    with request.app.state.engine.begin() as connection:
        problem = (
            WRONG_PASSWORD
            if not verify_password(user.password_hash, current_password)
            else PASSWORDS_DIFFER
            if new_password != confirmation
            else password_problem(new_password, user.email)
        )
        outcome = "rejected" if problem else "success"
        record_audit(connection, user.user_id, user.email, "password_change", outcome, address)
        if problem:
            return settings_page(request, connection, user, 400, password_error=problem)
        change_password(connection, user.user_id, hash_password(new_password), now)
        end_all_sessions(connection, user.user_id, keep_session_id=user.session_id)
    return redirect("/account?notice=password_changed")


@router.post("/2fa/start", response_class=HTMLResponse)
def start_two_factor(request: Request, user: SignedInUser = Depends(require_user)):
    secret = new_secret()
    with request.app.state.engine.begin() as connection:
        store_pending_totp_secret(connection, user.user_id, secret)
        record_audit(
            connection,
            user.user_id,
            user.email,
            "two_factor_setup_started",
            "success",
            client_address(request),
        )
        refreshed = replace(user, totp_secret=secret, is_totp_enabled=False, totp_last_step=None)
        return settings_page(
            request,
            connection,
            refreshed,
            setup_secret=secret,
            setup_qr=qr_code_svg(provisioning_uri(secret, user.email)),
        )


@router.post("/2fa/enable", response_class=HTMLResponse)
def enable_two_factor(request: Request, code: str = Form(""), user: SignedInUser = Depends(require_user)):
    address = client_address(request)
    with request.app.state.engine.begin() as connection:
        current = find_user(connection, user.user_id)
        step = accepted_step(current.totp_secret, code, None) if current and current.totp_secret else None
        outcome = "success" if step is not None else "wrong_code"
        record_audit(connection, user.user_id, user.email, "two_factor_enable", outcome, address)
        if step is None or current is None or current.totp_secret is None:
            secret = current.totp_secret if current else None
            qr = qr_code_svg(provisioning_uri(secret, user.email)) if secret else None
            return settings_page(
                request, connection, user, 400, setup_secret=secret, setup_qr=qr, setup_error=WRONG_CODE
            )
        enable_totp(connection, user.user_id, step)
        codes = new_recovery_codes()
        replace_recovery_codes(connection, user.user_id, [hash_token(c) for c in codes])
        enabled_user = replace(
            user, totp_secret=current.totp_secret, is_totp_enabled=True, totp_last_step=step
        )
        return settings_page(request, connection, enabled_user, new_recovery_codes=codes)


@router.post("/2fa/disable")
def disable_two_factor(
    request: Request, password: str = Form(""), user: SignedInUser = Depends(require_user)
):
    address = client_address(request)
    with request.app.state.engine.begin() as connection:
        if not verify_password(user.password_hash, password):
            record_audit(
                connection, user.user_id, user.email, "two_factor_disable", "wrong_password", address
            )
            return settings_page(request, connection, user, 400, two_factor_error=WRONG_PASSWORD)
        disable_totp(connection, user.user_id)
        delete_recovery_codes(connection, user.user_id)
        record_audit(connection, user.user_id, user.email, "two_factor_disable", "success", address)
    return redirect("/account?notice=two_factor_disabled")


@router.post("/2fa/recovery-codes", response_class=HTMLResponse)
def regenerate_recovery_codes(
    request: Request, password: str = Form(""), user: SignedInUser = Depends(require_user)
):
    address = client_address(request)
    with request.app.state.engine.begin() as connection:
        if not user.is_totp_enabled or not verify_password(user.password_hash, password):
            record_audit(
                connection, user.user_id, user.email, "recovery_codes_regenerate", "rejected", address
            )
            return settings_page(request, connection, user, 400, two_factor_error=WRONG_PASSWORD)
        codes = new_recovery_codes()
        replace_recovery_codes(connection, user.user_id, [hash_token(c) for c in codes])
        record_audit(connection, user.user_id, user.email, "recovery_codes_regenerate", "success", address)
        return settings_page(request, connection, user, new_recovery_codes=codes)


@router.get("/export")
def export_own_data(request: Request, user: SignedInUser = Depends(require_user)):
    """Everything held about this user, as JSON. Secrets (hash, 2FA seed, tokens) are not included."""
    with request.app.state.engine.begin() as connection:
        row = find_user(connection, user.user_id)
        invites_sent = [i for i in list_invites(connection) if i.invited_by == user.user_id]
        document = {
            "profile": export_profile(row) if row else {},
            "audit_log": export_audit_entries(connection, user.user_id),
            "invitations_sent": [
                {
                    "email": i.email,
                    "created_at": i.created_at.isoformat(),
                    "accepted": i.accepted_at is not None,
                }
                for i in invites_sent
            ],
            "exported_at": clock.utcnow().isoformat(),
        }
        record_audit(connection, user.user_id, user.email, "data_export", "success", client_address(request))
    return Response(
        json.dumps(document, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="process-analysis-my-data.json"'},
    )


@router.get("/delete", response_class=HTMLResponse)
def delete_confirmation_page(request: Request, user: SignedInUser = Depends(require_user)):
    """Step one of two: explain what will be lost. Nothing is deleted by visiting this page."""
    return render_page(request, "account_delete.html", user=user, delete_phrase=DELETE_PHRASE)


@router.post("/delete")
def delete_own_account(
    request: Request,
    password: str = Form(""),
    confirmation: str = Form(""),
    user: SignedInUser = Depends(require_user),
):
    """Step two: the password and the typed word must both be right."""
    address = client_address(request)
    with request.app.state.engine.begin() as connection:
        is_confirmed = verify_password(user.password_hash, password) and confirmation.strip() == DELETE_PHRASE
        if not is_confirmed:
            record_audit(connection, user.user_id, user.email, "account_delete", "rejected", address)
            return render_page(
                request,
                "account_delete.html",
                user=user,
                status_code=400,
                delete_phrase=DELETE_PHRASE,
                error="Wrong password, or the word was not typed exactly.",
            )
        record_audit(
            connection, user.user_id, user.email, "account_delete", "success", address, str(user.user_id)
        )
        delete_user(connection, user.user_id)
        erase_identity(connection, user.user_id)
    response = redirect("/?notice=account_deleted")
    clear_session_cookie(response, request.app.state.settings.is_cookie_secure)
    return response
