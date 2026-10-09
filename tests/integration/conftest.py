"""Integration tests run against a real Postgres named by TEST_DATABASE_URL.

Locally they skip when no database is configured. In CI, REQUIRE_DATABASE=1 turns that skip into
a failure, so a misconfigured pipeline cannot pass by silently testing nothing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]


def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        if os.environ.get("REQUIRE_DATABASE") == "1":
            pytest.fail("REQUIRE_DATABASE=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set")
    return url


def alembic_config(url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    os.environ["DATABASE_URL"] = url
    return config


@pytest.fixture
def migrated_database_url():
    """A schema rebuilt from nothing for each test: downgrade to base, then upgrade to head."""
    url = database_url()
    config = alembic_config(url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield url
    command.downgrade(config, "base")


@pytest.fixture
def engine(migrated_database_url):
    database_engine = create_engine(migrated_database_url)
    yield database_engine
    database_engine.dispose()


def table_names(database_engine) -> set[str]:
    with database_engine.connect() as connection:
        rows = connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        return {row[0] for row in rows}


# ---- Account-flow fixtures ---------------------------------------------------------------------

SITE = "http://testserver"
DEFAULT_PASSWORD = "walnut river lantern mosaic"


@pytest.fixture
def app(migrated_database_url):
    from web.app import create_app
    from web.settings import Settings

    settings = Settings(
        database_url=migrated_database_url,
        is_cookie_secure=False,
        public_base_url=SITE,
        enabled_providers=("openrouter", "deepseek"),
        sensitive_ok_providers=("openrouter",),
    )
    application = create_app(settings)
    yield application
    application.state.engine.dispose()


def new_browser(application):
    """A fresh cookie jar that sends same-site Origin headers like a real browser does."""
    from fastapi.testclient import TestClient

    return TestClient(application, base_url=SITE, headers={"Origin": SITE}, follow_redirects=False)


@pytest.fixture
def browser(app):
    with new_browser(app) as client:
        yield client


@pytest.fixture
def make_user(app):
    from web.passwords import hash_password
    from web.user_store import create_user

    def create(email="chris@example.com", password=DEFAULT_PASSWORD, is_admin=False):
        with app.state.engine.begin() as connection:
            return create_user(connection, email, hash_password(password), is_admin=is_admin)

    return create


def log_in(client, email="chris@example.com", password=DEFAULT_PASSWORD):
    return client.post("/login", data={"email": email, "password": password})
