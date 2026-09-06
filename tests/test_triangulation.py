"""Triangulation must not depend on a model's judgment about ambiguous scope."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analyzer.triangulation import (  # noqa: E402
    aliases_for,
    is_hypothesis_about_another,
    named_counterparties,
)

RAINER = aliases_for("rainer", "Rainer Hoffmann")


def claim(kind: str, payload: dict, scope: str = "self", refs=None) -> dict:
    return {"kind": kind, "payload": payload, "subject_scope": scope, "entity_refs": refs or []}


def test_waiting_on_another_person_is_a_hypothesis_despite_self_scope():
    """The case that motivated this module: 'I'm waiting on Petra', marked self.

    The waiting is direct experience; the attribution is inference. An extractor labelling
    the whole claim `self` is answering an ambiguous question, so the fracture detector
    cannot rely on that label.
    """
    waiting = claim("wait", {"waiting_on": "Petra", "owner": "internal"}, scope="self")
    assert is_hypothesis_about_another(waiting, RAINER)
    assert named_counterparties(waiting, RAINER) == ["Petra"]


def test_chasing_and_rework_from_another_person_also_count():
    assert is_hypothesis_about_another(
        claim("handoff", {"from": "Rainer", "to": "Petra"}), RAINER
    )
    assert is_hypothesis_about_another(
        claim("rework", {"what": "availability", "returned_by": "Petra"}), RAINER
    )


def test_self_reference_is_not_a_counterparty():
    """Naming yourself, by id, full name or first name, is not an assertion about another."""
    for self_name in ("rainer", "Rainer Hoffmann", "Rainer"):
        assert not is_hypothesis_about_another(
            claim("handoff", {"from": self_name, "to": self_name}), RAINER
        )


def test_purely_internal_claim_is_not_a_hypothesis():
    assert not is_hypothesis_about_another(
        claim("duration", {"measure": "touch", "value": {"low": 5, "high": 10, "unit": "minute"},
                           "basis": "typical"}), RAINER
    )


def test_actor_and_team_mentions_become_candidates():
    tagged = claim("wait", {"waiting_on": "an answer", "owner": "internal"},
                   refs=[{"text": "legal", "type": "team", "role": "waiting_on"}])
    assert named_counterparties(tagged, RAINER) == ["an answer", "legal"]


def test_artifact_entity_refs_do_not_become_candidates():
    """Only people and teams can contradict you, so only they are read from entity_refs."""
    tagged = claim("wait", {"waiting_on": "the statement", "owner": "external"},
                   refs=[{"text": "the bank statement", "type": "artifact", "role": "waiting_on"}])
    assert "the bank statement" not in named_counterparties(tagged, RAINER)


def test_candidates_may_include_things_pending_resolution():
    """A payload string is a candidate, not a resolved actor. Filtering is the resolver's job."""
    vague = claim("wait", {"waiting_on": "availability information", "owner": "internal"})
    assert named_counterparties(vague, RAINER) == ["availability information"]


def test_detects_the_planted_fracture_in_real_extracted_claims():
    """End to end, on claims actually extracted from the false-blame holder's transcript."""
    probe = REPO_ROOT / "tests" / "fixtures" / "rainer_claims.json"
    if not probe.exists():
        import pytest

        pytest.skip("extraction fixture not present")
    claims = json.loads(probe.read_text())
    blamed = [
        name
        for one in claims
        for name in named_counterparties(one, RAINER)
        if name.lower().startswith("petra")
    ]
    assert blamed, "the planted false-blame target was not detected in any claim"
