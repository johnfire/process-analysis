"""The score ratchet: the analyzer must keep recovering what it recovers today.

Each (process, analyzer) pair is scored against its hidden ground truth. Criteria that pass now
must keep passing. Criteria that fail now are strict xfails: if one starts passing, the run fails
until it is moved into the passing set, so an improvement is recorded rather than lost.

Baseline recorded 2026-10-07 (DeepSeek claims 11/14, codex claims 9/14).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzer import metrics as metrics_module
from analyzer.cli import load
from analyzer.score import score

SEED_ROOT = Path(__file__).resolve().parents[1] / "corpus" / "seed"

KNOWN_FAILING = {
    ("hospital-onboarding", "claims"): {"external_share_within_20_points", "batch_delay_surfaced"},
    ("hospital-onboarding", "claims-codex"): {"external_share_within_20_points", "batch_delay_surfaced"},
    ("inbound-lead-to-qualified-contact", "claims"): {"delay_ranking_correlates"},
    ("inbound-lead-to-qualified-contact", "claims-codex"): {
        "external_share_within_20_points",
        "delay_ranking_correlates",
        "batch_delay_surfaced",
    },
}

CRITERIA = (
    "bottleneck_in_top_three",
    "decoy_not_ranked_first",
    "external_share_within_20_points",
    "cycle_efficiency_under_5_percent",
    "delay_ranking_correlates",
    "batch_delay_surfaced",
    "delay_ranking_differs_from_complaints",
)


def scored_criteria(process_name: str, claims_dirname: str) -> dict[str, bool]:
    ground_truth, _, _, _, graph = load(SEED_ROOT / process_name, claims_dirname)
    criteria = score(metrics_module.compute(graph), ground_truth)
    return {criterion.name: criterion.passed for criterion in criteria}


def ratchet_cases():
    for (process_name, claims_dirname), failing in KNOWN_FAILING.items():
        for criterion_name in CRITERIA:
            marks = []
            if criterion_name in failing:
                marks.append(pytest.mark.xfail(strict=True, reason="known gap; promote when fixed"))
            yield pytest.param(
                process_name, claims_dirname, criterion_name,
                id=f"{process_name}-{claims_dirname}-{criterion_name}",
                marks=marks,
            )


def test_criteria_list_matches_scorer():
    scored = scored_criteria("hospital-onboarding", "claims")
    assert set(scored) == set(CRITERIA), "scorer criteria changed; update the ratchet"


@pytest.mark.parametrize(("process_name", "claims_dirname", "criterion_name"), list(ratchet_cases()))
def test_criterion_holds(process_name, claims_dirname, criterion_name):
    assert scored_criteria(process_name, claims_dirname)[criterion_name]
