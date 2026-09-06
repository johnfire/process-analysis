"""The information barrier must hold structurally, not by instruction.

A cast member's slice is the only thing their model ever sees. If the answer key, another
person's timings, or the end-to-end shape of the process leak into it, the eval still
produces numbers and those numbers are worthless. These tests are the guard.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "corpus"))

from generate import build_slice  # noqa: E402

SEED_ROOT = REPO_ROOT / "corpus" / "seed"


def all_ground_truths() -> list[Path]:
    return sorted(SEED_ROOT.glob("*/ground_truth.json"))


@pytest.fixture(params=all_ground_truths(), ids=lambda path: path.parent.name)
def ground_truth(request) -> dict:
    return json.loads(request.param.read_text())


def every_slice(ground_truth: dict):
    for member in ground_truth["cast"]:
        yield member, build_slice(ground_truth, member["person_id"])


def test_answer_key_never_reaches_a_slice(ground_truth):
    """No slice may contain the planted block or any classification label."""
    for member, person_slice in every_slice(ground_truth):
        serialised = json.dumps(person_slice)
        assert "planted" not in serialised, member["person_id"]
        assert "true_classification" not in serialised, member["person_id"]
        for planted_key in ground_truth["planted"]:
            assert planted_key not in serialised, f"{member['person_id']} sees {planted_key}"


def test_nobody_sees_another_persons_timings(ground_truth):
    """Durations are knowable only for your own steps."""
    for member, person_slice in every_slice(ground_truth):
        own_step_ids = {step["step_id"] for step in person_slice["your_steps"]}
        expected = {
            step["step_id"]
            for step in ground_truth["steps"]
            if step["performed_by"] == member["person_id"]
        }
        assert own_step_ids == expected, member["person_id"]

        adjacent = person_slice["work_arrives_from"] + person_slice["work_departs_to"]
        for entry in adjacent:
            assert "touch_minutes" not in entry
            assert "queue_before_minutes" not in entry


def test_nobody_sees_the_whole_process(ground_truth):
    """No single respondent may hold the end-to-end shape; that is what the analyzer is for."""
    total_steps = len(ground_truth["steps"])
    for member, person_slice in every_slice(ground_truth):
        assert len(person_slice["your_steps"]) < total_steps, (
            f"{member['person_id']} can see the entire process"
        )


def test_false_blame_reaches_exactly_one_person(ground_truth):
    """The planted misapprehension is held by its holder alone, and by nobody else."""
    holder = ground_truth["planted"]["false_blame"]["claimed_by"]
    believers = [
        member["person_id"]
        for member, person_slice in every_slice(ground_truth)
        if person_slice["you_believe_you_are_blocked_by"] is not None
    ]
    assert believers == [holder]


def test_queue_gap_is_not_computable_by_any_individual(ground_truth):
    """The central metric must require two accounts. If one person holds it, it is not a finding."""
    steps_by_id = {step["step_id"]: step for step in ground_truth["steps"]}
    crossing_handoffs = [
        step
        for step in ground_truth["steps"]
        if step.get("hands_to")
        and steps_by_id[step["hands_to"]]["performed_by"] != step["performed_by"]
        and steps_by_id[step["hands_to"]]["queue_before_minutes"] > 0
    ]
    assert crossing_handoffs, "no cross-person handoff carries a queue; nothing to triangulate"

    for handoff in crossing_handoffs:
        downstream = steps_by_id[handoff["hands_to"]]
        upstream_slice = build_slice(ground_truth, handoff["performed_by"])
        visible = {step["step_id"] for step in upstream_slice["your_steps"]}
        assert downstream["step_id"] not in visible, (
            f"{handoff['performed_by']} can see the queue after their own handoff"
        )


def test_lopsidedness_is_severe(ground_truth):
    """A process whose work time approaches its elapsed time tests nothing interesting."""
    touch = sum(step["touch_minutes"] for step in ground_truth["steps"])
    queue = sum(step["queue_before_minutes"] for step in ground_truth["steps"])
    efficiency = touch / (touch + queue)
    assert efficiency < 0.05, f"cycle efficiency {efficiency:.2%} is too healthy to be realistic"


def test_false_blame_attaches_to_a_real_step(ground_truth):
    """The misapprehension must be about work both parties actually do.

    A false-blame narrative describing an activity that is not a step reaches neither
    person's slice, so neither mentions it and the fracture never appears in the testimony.
    The answer key then names a contradiction the corpus does not contain.
    """
    false_blame = ground_truth["planted"]["false_blame"]
    step_id = false_blame.get("step_id")
    if step_id is None:
        pytest.skip("predates the guard; see corpus/README.md")
    steps_by_id = {step["step_id"]: step for step in ground_truth["steps"]}
    assert step_id in steps_by_id, f"false_blame names unknown step {step_id}"
    assert steps_by_id[step_id]["performed_by"] == false_blame["blames"], (
        "the blamed person must actually perform the step they are blamed for"
    )
