"""Load the synthetic corpus into the database so the viewer has something to show.

Safe to run on every deploy: a process, a claim set or a result that is already stored is left
alone. A new analyzer version adds a new result next to the old one. Each process is imported in
its own transaction, so one bad directory cannot stop the others.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import Connection, Engine

from analyzer.analysis import ANALYZER_VERSION
from analyzer.result_document import document_from_ground_truth
from web import process_store

CORPUS_ROOT = Path(__file__).resolve().parents[1] / "corpus" / "seed"
SYNTHETIC_CLIENT_NAME = "Synthetic corpus"

log = logging.getLogger(__name__)


@dataclass
class ImportReport:
    imported: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def claim_set_directories(process_dir: Path) -> list[Path]:
    """Directories of per-respondent claim files: `claims`, `claims-codex`, ..."""
    found = [
        p
        for p in process_dir.iterdir()
        if p.is_dir() and (p.name == "claims" or p.name.startswith("claims-"))
    ]
    return sorted(found)


def read_claims(claim_dir: Path) -> dict[str, list[dict]]:
    return {path.stem: json.loads(path.read_text()) for path in sorted(claim_dir.glob("*.json"))}


def read_transcripts(process_dir: Path) -> dict[str, str]:
    folder = process_dir / "transcripts"
    return {path.stem: path.read_text() for path in sorted(folder.glob("*.md"))} if folder.exists() else {}


def ensure_synthetic_client(connection: Connection):
    existing = process_store.find_synthetic_client(connection, SYNTHETIC_CLIENT_NAME)
    return existing or process_store.create_client(connection, SYNTHETIC_CLIENT_NAME, None, True)


def import_process(connection: Connection, client_id, process_dir: Path) -> None:
    ground_truth = json.loads((process_dir / "ground_truth.json").read_text())
    slug = process_dir.name
    process_id = process_store.find_process_by_slug(connection, client_id, slug)
    if process_id is None:
        process_id = process_store.create_process(
            connection,
            client_id=client_id,
            slug=slug,
            name=ground_truth["organisation"]["name"],
            domain=ground_truth["domain"],
            organisation=ground_truth["organisation"],
            cast=ground_truth["cast"],
            ground_truth=ground_truth,
        )
        process_store.add_transcripts(connection, process_id, read_transcripts(process_dir))
    for claim_dir in claim_set_directories(process_dir):
        claim_set = claim_dir.name
        grouped = read_claims(claim_dir)
        if not process_store.has_claim_set(connection, process_id, claim_set):
            process_store.add_claims(connection, process_id, claim_set, grouped)
        if not process_store.has_result(connection, process_id, claim_set, ANALYZER_VERSION):
            document = document_from_ground_truth(ground_truth, claim_set, grouped)
            process_store.add_result(connection, process_id, claim_set, ANALYZER_VERSION, document)


def import_seed_processes(engine: Engine, corpus_root: Path = CORPUS_ROOT) -> ImportReport:
    report = ImportReport()
    with engine.begin() as connection:
        client_id = ensure_synthetic_client(connection)
    for process_dir in sorted(p for p in corpus_root.iterdir() if (p / "ground_truth.json").exists()):
        try:
            with engine.begin() as connection:
                import_process(connection, client_id, process_dir)
            report.imported.append(process_dir.name)
        except Exception:
            log.exception("importing %s failed", process_dir.name)
            report.failed.append(process_dir.name)
    return report
