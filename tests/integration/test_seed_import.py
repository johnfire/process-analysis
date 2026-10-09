"""Loading the synthetic corpus: complete, repeatable, and isolated per process."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import text

from analyzer.analysis import ANALYZER_VERSION
from web.seed_import import CORPUS_ROOT, SYNTHETIC_CLIENT_NAME, import_seed_processes


def count(engine, sql: str) -> int:
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


def test_both_seed_processes_arrive_with_everything_the_viewer_needs(app):
    report = import_seed_processes(app.state.engine)
    assert (
        sorted(report.imported) == ["hospital-onboarding", "inbound-lead-to-qualified-contact"]
        and not report.failed
    )
    engine = app.state.engine
    assert count(engine, "SELECT count(*) FROM processes") == 2
    assert count(engine, "SELECT count(*) FROM transcripts") == 14
    assert count(engine, "SELECT count(DISTINCT claim_set) FROM claims") == 2
    assert count(engine, "SELECT count(*) FROM results") == 4
    assert count(engine, "SELECT count(*) FROM clients WHERE owner_user_id IS NULL AND is_synthetic") == 1


def test_importing_again_changes_nothing(app):
    import_seed_processes(app.state.engine)
    before = [
        count(app.state.engine, f"SELECT count(*) FROM {t}")
        for t in ("clients", "processes", "claims", "results")
    ]
    import_seed_processes(app.state.engine)
    after = [
        count(app.state.engine, f"SELECT count(*) FROM {t}")
        for t in ("clients", "processes", "claims", "results")
    ]
    assert before == after


def test_a_new_analyzer_version_adds_a_result_and_keeps_the_old_one(app, monkeypatch):
    import_seed_processes(app.state.engine)
    monkeypatch.setattr("web.seed_import.ANALYZER_VERSION", ANALYZER_VERSION + "-next")
    import_seed_processes(app.state.engine)
    assert count(app.state.engine, "SELECT count(*) FROM results") == 8
    assert (
        count(app.state.engine, f"SELECT count(*) FROM results WHERE analyzer_version = '{ANALYZER_VERSION}'")
        == 4
    )


def test_stored_claims_match_the_files_they_came_from(app):
    import_seed_processes(app.state.engine)
    files = sum(
        len(__import__("json").loads(p.read_text()))
        for p in (CORPUS_ROOT / "hospital-onboarding" / "claims").glob("*.json")
    )
    assert (
        count(
            app.state.engine,
            "SELECT count(*) FROM claims c JOIN processes p ON p.id = c.process_id "
            "WHERE p.slug = 'hospital-onboarding' AND c.claim_set = 'claims'",
        )
        == files
    )


def test_one_broken_process_does_not_stop_the_others(app, tmp_path: Path):
    corpus = tmp_path / "seed"
    shutil.copytree(CORPUS_ROOT, corpus)
    (corpus / "hospital-onboarding" / "ground_truth.json").write_text("{not json")
    report = import_seed_processes(app.state.engine, corpus)
    assert report.failed == ["hospital-onboarding"]
    assert report.imported == ["inbound-lead-to-qualified-contact"]
    assert count(app.state.engine, "SELECT count(*) FROM processes") == 1


def test_the_synthetic_client_is_shared_and_named(app):
    import_seed_processes(app.state.engine)
    assert (
        count(app.state.engine, f"SELECT count(*) FROM clients WHERE name = '{SYNTHETIC_CLIENT_NAME}'") == 1
    )
