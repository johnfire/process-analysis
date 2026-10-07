"""FastAPI application factory."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.database import create_database_engine
from web.health import check_health, head_revision_of
from web.settings import Settings, settings_from_environment
from web.structured_logging import configure_logging, correlation_id, new_correlation_id

PACKAGE_DIR = Path(__file__).resolve().parent
CORRELATION_HEADER = "X-Request-ID"

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or settings_from_environment()
    configure_logging(active_settings.log_level)

    app = FastAPI(title="Process Analysis", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = active_settings
    app.state.engine = create_database_engine(active_settings.database_url)
    app.state.head_revision = head_revision_of()
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

    app.middleware("http")(attach_correlation_id)
    register_routes(app, templates)
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


def register_routes(app: FastAPI, templates: Jinja2Templates) -> None:
    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request):
        return templates.TemplateResponse(request, "landing.html")

    @app.get("/health")
    def health():
        stale_after = timedelta(seconds=app.state.settings.worker_stale_after_seconds)
        report = check_health(app.state.engine, app.state.head_revision, stale_after)
        if not report.is_healthy:
            log.warning("unhealthy: %s", report.checks)
        status = "ok" if report.is_healthy else "degraded"
        return JSONResponse({"status": status, "checks": report.checks},
                            status_code=200 if report.is_healthy else 503)
