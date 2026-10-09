"""The session cookie: HttpOnly so scripts cannot read it, SameSite=Lax so other sites cannot send it."""

from __future__ import annotations

from fastapi import Request, Response

from web.session_store import SESSION_LIFETIME

COOKIE_NAME = "pa_session"


def set_session_cookie(response: Response, raw_token: str, is_secure: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw_token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, is_secure: bool) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=is_secure, samesite="lax")


def read_session_token(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)
