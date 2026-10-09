"""The table definitions the app queries must be exactly what the migrations build."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from web.database import metadata


def test_live_table_definitions_match_the_migrated_database(engine):
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, metadata)
    assert differences == []
