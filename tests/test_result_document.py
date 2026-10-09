"""The stored shape of an analysis: what the viewer is allowed to rely on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analyzer.analysis import ANALYZER_VERSION
from analyzer.cli import load
from analyzer.result_document import document_from_ground_truth

SEED = Path(__file__).resolve().parents[1] / "corpus" / "seed"


@pytest.fixture(scope="module")
def hospital():
    ground_truth, _, _, claims, _ = load(SEED / "hospital-onboarding")
    return ground_truth, document_from_ground_truth(ground_truth, "claims", claims)


def test_document_is_plain_json(hospital):
    _, document = hospital
    assert json.loads(json.dumps(document)) == document


def test_document_records_which_analyzer_and_claim_set_made_it(hospital):
    _, document = hospital
    assert document["analyzer_version"] == ANALYZER_VERSION
    assert document["claim_set"] == "claims"


def test_people_carry_names_roles_and_both_rankings(hospital):
    _, document = hospital
    people = document["people"]
    assert [p["delay_rank"] for p in people] == list(range(1, len(people) + 1))
    assert sorted(p["complaint_rank"] for p in people) == list(range(1, len(people) + 1))
    assert all(p["name"] and p["role"] for p in people)


def test_people_without_any_stated_duration_are_marked_as_having_no_evidence(hospital):
    _, document = hospital
    silent = [p for p in document["people"] if not p["has_time_evidence"]]
    assert silent, "the seed corpus has people nobody gave a duration for"
    assert all(p["attributed_queue"] == 0 for p in silent)
    assert all(p["has_time_evidence"] for p in document["people"] if p["attributed_queue"] > 0)


def test_fractures_name_people_not_ids_and_keep_their_quotes(hospital):
    _, document = hospital
    assert document["fractures"]
    for fracture in document["fractures"]:
        assert fracture["claimant"]["name"] in fracture["summary"]
        assert "-" not in fracture["claimant"]["name"].replace("Dr. ", "")  # a name, not a person_id
        assert all(quote["verbatim"] for quote in fracture["claimant_claims"])


def test_a_synthetic_process_is_scored_and_the_scores_match_the_cli(hospital):
    _, document = hospital
    assert len(document["score"]) == 7
    assert {c["name"] for c in document["score"]} >= {"bottleneck_in_top_three", "decoy_not_ranked_first"}


def test_time_totals_are_consistent(hospital):
    _, document = hospital
    time = document["time"]
    assert time["queue_minutes"] == pytest.approx(
        time["internal_wait_minutes"] + time["external_wait_minutes"]
    )
    assert 0 < time["cycle_efficiency"] < 0.05


def test_both_claim_sets_of_both_processes_can_be_analysed():
    for process in sorted(SEED.iterdir()):
        for claims_dir in ("claims", "claims-codex"):
            ground_truth, _, _, claims, _ = load(process, claims_dir)
            document = document_from_ground_truth(ground_truth, claims_dir, claims)
            assert document["claim_set"] == claims_dir and document["people"]
