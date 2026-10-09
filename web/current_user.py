"""Who is making this request, resolved from the session cookie."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request

from web import clock
from web.one_time_tokens import hash_token
from web.session_cookie import read_session_token
from web.session_store import find_live_session


@dataclass(frozen=True)
class SignedInUser:
    session_id: UUID
    user_id: UUID
    email: str
    is_admin: bool
    is_totp_enabled: bool
    totp_secret: str | None
    totp_last_step: int | None
    password_hash: str
    is_mfa_verified: bool


class LoginRequired(Exception):
    """Raised to send an anonymous visitor to the login page."""


def client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def load_session_user(request: Request) -> SignedInUser | None:
    """The user behind this request's cookie, including a password-only session awaiting its code."""
    raw_token = read_session_token(request)
    if not raw_token:
        return None
    with request.app.state.engine.connect() as connection:
        row = find_live_session(connection, hash_token(raw_token), clock.utcnow())
    if row is None:
        return None
    return SignedInUser(
        session_id=row.session_id,
        user_id=row.user_id,
        email=row.email,
        is_admin=row.is_admin,
        is_totp_enabled=row.is_totp_enabled,
        totp_secret=row.totp_secret,
        totp_last_step=row.totp_last_step,
        password_hash=row.password_hash,
        is_mfa_verified=row.is_mfa_verified,
    )


def require_user(request: Request) -> SignedInUser:
    user = load_session_user(request)
    if user is None or not user.is_mfa_verified:
        raise LoginRequired
    return user


def require_admin(request: Request) -> SignedInUser:
    user = require_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrators only")
    return user
