"""Process lookup: typing a full corpus path every time is what stops a tool being used."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analyzer.cli import find_process  # noqa: E402


def test_exact_name_resolves():
    assert find_process("hospital-onboarding").name == "hospital-onboarding"


def test_unambiguous_prefix_resolves():
    assert find_process("hospital").name == "hospital-onboarding"


def test_substring_resolves_when_no_prefix_matches():
    assert find_process("qualified").name == "inbound-lead-to-qualified-contact"


def test_a_real_path_still_works():
    path = REPO_ROOT / "corpus" / "seed" / "hospital-onboarding"
    assert find_process(str(path)) == path


def test_ambiguous_abbreviation_lists_candidates_rather_than_guessing():
    with pytest.raises(SystemExit) as caught:
        find_process("o")
    assert "ambiguous" in str(caught.value)
    assert "hospital-onboarding" in str(caught.value)


def test_unknown_name_lists_what_is_available():
    with pytest.raises(SystemExit) as caught:
        find_process("payroll")
    assert "no such process" in str(caught.value)
