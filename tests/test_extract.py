"""Tests for the deterministic half of claim extraction.

The model call is not tested here. Everything that guards its output is.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analyzer.extract import (  # noqa: E402
    extract_json_array,
    is_grounded,
    normalise,
    validate_claims,
)

TRANSCRIPT = (
    "**Interviewer:** What are you waiting on right now?\n\n"
    "**Anna Schmidt:** Nothing on my bit, really. Once an inquiry hits the form or the inbox, "
    "it should just make the lead in Dynamics and move along — although she’ll say "
    "it’s the CRM, obviously."
)


class TestGrounding:
    def test_exact_quotation_is_grounded(self):
        assert is_grounded("Nothing on my bit, really.", TRANSCRIPT)

    def test_typographic_punctuation_does_not_break_grounding(self):
        """Quoting speech back through a model routinely swaps quotes and dashes."""
        assert is_grounded("although she'll say it's the CRM, obviously", TRANSCRIPT)

    def test_whitespace_and_case_differences_are_tolerated(self):
        assert is_grounded("nothing on my   bit,\nreally", TRANSCRIPT)

    def test_paraphrase_is_not_grounded(self):
        """The failure this check exists to catch: a plausible quote nobody said."""
        assert not is_grounded("I am not waiting on anything at the moment.", TRANSCRIPT)

    def test_invented_detail_is_not_grounded(self):
        assert not is_grounded("it takes about three days in Dynamics", TRANSCRIPT)

    def test_empty_verbatim_is_never_grounded(self):
        assert not is_grounded("", TRANSCRIPT) or normalise("") == ""


class TestOutputParsing:
    def test_bare_array(self):
        assert extract_json_array('[{"id": "a"}]') == [{"id": "a"}]

    def test_fenced_array(self):
        assert extract_json_array('Here you go:\n```json\n[{"id": "a"}]\n```\nDone.') == [{"id": "a"}]

    def test_array_with_surrounding_chatter(self):
        assert extract_json_array('Sure.\n[{"id": "a"}]\nLet me know.') == [{"id": "a"}]

    def test_no_array_raises(self):
        with pytest.raises(ValueError):
            extract_json_array("I could not find any claims.")


class TestSchemaValidation:
    @staticmethod
    def claim(**overrides) -> dict:
        base = {
            "id": "r1-001",
            "respondent_id": "r1",
            "session_id": "s1",
            "captured_at": "2026-09-06T10:00:00Z",
            "kind": "wait",
            "verbatim": "waiting on legal",
            "hedging": "firm",
            "polarity": "asserted",
            "subject_scope": "hearsay",
            "payload": {"waiting_on": "legal", "owner": "internal"},
        }
        base.update(overrides)
        return base

    def test_valid_claim_passes(self):
        valid, invalid = validate_claims([self.claim()])
        assert len(valid) == 1 and not invalid

    def test_bad_payload_is_separated_not_dropped_silently(self):
        valid, invalid = validate_claims([self.claim(payload={"waiting_on": "legal"})])
        assert not valid
        assert len(invalid) == 1 and "owner" in invalid[0][1]

    def test_mixed_batch_keeps_the_good_ones(self):
        valid, invalid = validate_claims([self.claim(), self.claim(hedging="vague")])
        assert len(valid) == 1 and len(invalid) == 1
