"""Pages and middleware, with no database: a broken database must not break the landing page."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.app import CORRELATION_HEADER, create_app
from web.health import head_revision_of
from web.settings import Settings, settings_from_environment

# Port 1 refuses at once, so the health probe fails fast instead of waiting on a timeout.
UNREACHABLE_DATABASE = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none?connect_timeout=1"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(Settings(database_url=UNREACHABLE_DATABASE)))


def test_landing_page_renders_without_database(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "17 minutes" in response.text
    assert "Impressum" in response.text


def test_static_assets_are_served(client):
    assert client.get("/static/site.css").status_code == 200
    assert client.get("/static/icon.svg").status_code == 200


def test_health_reports_unreachable_database_as_503(client):
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unreachable"


def test_correlation_id_is_minted_when_absent(client):
    minted = client.get("/").headers[CORRELATION_HEADER]
    assert len(minted) == 32


def test_usable_correlation_id_is_echoed(client):
    supplied = "abc12345-6789"
    assert client.get("/", headers={CORRELATION_HEADER: supplied}).headers[CORRELATION_HEADER] == supplied


def test_hostile_correlation_id_is_replaced(client):
    hostile = "x\r\nSet-Cookie: evil"
    assert client.get("/", headers={CORRELATION_HEADER: hostile}).headers[CORRELATION_HEADER] != hostile


def test_missing_database_url_stops_startup():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        settings_from_environment({})


def test_migrations_have_a_single_head():
    assert head_revision_of() == "0001"
