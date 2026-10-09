"""Template rendering shared by every page."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from analyzer.formatting import human
from web.current_user import SignedInUser

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
templates.env.filters["human_minutes"] = human

# Notices travel as a fixed key in the query string and map to fixed text, so no page ever echoes
# attacker-controlled text.
NOTICES = {
    "password_reset": "Your password was changed. Log in with the new one.",
    "invite_accepted": "Your account is ready. Log in to continue.",
    "signed_out": "You are signed out.",
    "account_deleted": "Your account and its data were deleted.",
    "password_changed": "Password changed. Other devices were signed out.",
    "two_factor_disabled": "Two-factor authentication is off.",
    "codes_regenerated": "New recovery codes issued; the old ones no longer work.",
    "invite_sent": "Invitation sent.",
}


def render_page(
    request: Request, template: str, user: SignedInUser | None = None, status_code: int = 200, **context
) -> HTMLResponse:
    notice = NOTICES.get(request.query_params.get("notice", ""))
    return templates.TemplateResponse(
        request, template, {"user": user, "notice": notice, **context}, status_code=status_code
    )
