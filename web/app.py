"""FastAPI application factory."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError

from web import account_routes, invite_routes, login_routes, recovery_routes
from web.current_user import LoginRequired, load_session_user
from web.database import create_database_engine
from web.health import check_health, head_revision_of
from web.page_rendering import PACKAGE_DIR, render_page
from web.request_origin import host_of, is_same_origin, needs_origin_check
from web.settings import Settings, settings_from_environment
from web.structured_logging import configure_logging, correlation_id, new_correlation_id

CORRELATION_HEADER = "X-Request-ID"
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
}

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or settings_from_environment()
    configure_logging(active_settings.log_level)

    app = FastAPI(title="Process Analysis", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = active_settings
    app.state.engine = create_database_engine(active_settings.database_url)
    app.state.head_revision = head_revision_of()
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    app.middleware("http")(reject_cross_site_writes)
    app.middleware("http")(add_security_headers)
    app.middleware("http")(attach_correlation_id)
    for router in (login_routes.router, recovery_routes.router, account_routes.router, invite_routes.router):
        app.include_router(router)
    register_routes(app)
    register_error_handlers(app)
    return app


async def attach_correlation_id(request: Request, call_next):
    """Reuse a caller's request ID when it looks sane, otherwise mint one; echo it back."""
    supplied = request.headers.get(CORRELATION_HEADER, "")
    is_usable = 8 <= len(supplied) <= 64 and supplied.replace("-", "").isalnum()
    token = correlation_id.set(supplied if is_usable else new_correlation_id())
    try:
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id.get()
        return response
    finally:
        correlation_id.reset(token)


async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


async def reject_cross_site_writes(request: Request, call_next):
    if needs_origin_check(request.method):
        own_hosts = {
            request.headers.get("host", "").lower(),
            host_of(request.app.state.settings.public_base_url),
        }
        if not is_same_origin(request.headers.get("origin"), request.headers.get("referer"), own_hosts):
            log.warning("refused cross-site %s %s", request.method, request.url.path)
            return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    return await call_next(request)


def register_routes(app: FastAPI) -> None:
    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request):
        return render_page(request, "landing.html", user=load_session_user_safely(request))

    @app.get("/health")
    def health():
        stale_after = timedelta(seconds=app.state.settings.worker_stale_after_seconds)
        report = check_health(app.state.engine, app.state.head_revision, stale_after)
        if not report.is_healthy:
            log.warning("unhealthy: %s", report.checks)
        status = "ok" if report.is_healthy else "degraded"
        return JSONResponse(
            {"status": status, "checks": report.checks}, status_code=200 if report.is_healthy else 503
        )


def load_session_user_safely(request: Request):
    """The landing page must render even with the database down, so a failed lookup means 'anonymous'."""
    try:
        user = load_session_user(request)
    except OperationalError:
        log.exception("session lookup failed; serving the landing page anonymously")
        return None
    return user if user and user.is_mfa_verified else None


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LoginRequired)
    def send_to_login(request: Request, _: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(OperationalError)
    def database_unavailable(request: Request, error: OperationalError):
        log.error("database unavailable while serving %s", request.url.path)
        return render_page(request, "unavailable.html", status_code=503)

    @app.exception_handler(HTTPException)
    def show_http_error(request: Request, error: HTTPException):
        if error.status_code == 403 and "text/html" in request.headers.get("accept", ""):
            return render_page(request, "forbidden.html", status_code=403)
        return JSONResponse({"detail": error.detail}, status_code=error.status_code)
