"""Fracture detection must find silences, not only contradictions."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analyzer.fracture import find_fractures  # noqa: E402
from analyzer.resolve import Person, build_person_index, resolve_person  # noqa: E402
from analyzer.triangulation import aliases_for, named_counterparties  # noqa: E402


def claim(kind: str, verbatim: str = "x") -> dict:
    return {"kind": kind, "verbatim": verbatim, "payload": {}, "subject_scope": "self"}


class TestShapes:
    def test_one_sided_dependency_is_a_silence(self):
        found = find_fractures({("rainer", "petra"): [claim("wait")]})
        assert [(f.kind, f.claimant, f.counterparty) for f in found] == [
            ("silence", "rainer", "petra")
        ]

    @staticmethod
    def waited(low, high, unit="day"):
        return {
            "kind": "wait", "verbatim": "x", "subject_scope": "self",
            "payload": {"waiting_on": "them", "owner": "internal",
                        "duration": {"low": low, "high": high, "unit": unit}},
        }

    def test_mutual_accounts_that_disagree_are_a_contradiction(self):
        found = find_fractures(
            {("petra", "andrea"): [self.waited(3, 5)],
             ("andrea", "petra"): [self.waited(10, 30, "minute")]}
        )
        assert len(found) == 1 and found[0].kind == "contradiction"

    def test_a_contradiction_is_reported_once_not_twice(self):
        found = find_fractures(
            {("a", "b"): [self.waited(4, 6)], ("b", "a"): [self.waited(5, 10, "minute")]}
        )
        assert len(found) == 1

    def test_passing_mention_without_a_channel_is_not_a_fracture(self):
        """Naming a colleague is not a relationship. Reporting it would bury real findings."""
        assert find_fractures({("rainer", "petra"): [claim("actor"), claim("complaint")]}) == []

    def test_people_who_never_mention_each_other_are_not_a_fracture(self):
        assert find_fractures({}) == []


class TestAgainstCorpus:
    @staticmethod
    def mentions_for(process_dir: Path):
        ground_truth = json.loads((process_dir / "ground_truth.json").read_text())
        cast = [Person(m["person_id"], m["name"], m["role"]) for m in ground_truth["cast"]]
        index = build_person_index(cast)
        by_id = {m["person_id"]: m for m in ground_truth["cast"]}
        mentions = defaultdict(list)
        for claims_path in sorted((process_dir / "claims").glob("*.json")):
            speaker = claims_path.stem
            speaker_aliases = aliases_for(speaker, by_id[speaker]["name"])
            for one in json.loads(claims_path.read_text()):
                for mention in named_counterparties(one, speaker_aliases):
                    subject = resolve_person(mention, index)
                    if subject:
                        mentions[(speaker, subject)].append(one)
        return ground_truth, dict(mentions)

    def planted_fracture(self, process_dir: Path):
        ground_truth, mentions = self.mentions_for(process_dir)
        planted = ground_truth["planted"]["false_blame"]
        pair = {planted["claimed_by"], planted["blames"]}
        found = find_fractures(mentions)
        return found, [f for f in found if {f.claimant, f.counterparty} == pair]

    def test_silence_shaped_plant_is_detected_end_to_end(self):
        """The decisive check: raw transcripts through to a located fracture, in code alone.

        In this corpus the blamed party has genuinely never heard of the sender - his emails
        go to a distribution alias nobody reads - so her account contains no trace of him.
        The silence is the evidence.
        """
        found, involved = self.planted_fracture(
            REPO_ROOT / "corpus" / "seed" / "inbound-lead-to-qualified-contact"
        )
        assert involved, "planted fracture not detected"
        assert involved[0].kind == "silence"

    def test_detector_is_selective_not_indiscriminate(self):
        """Flagging every working relationship is the same as flagging none."""
        for process_dir in sorted((REPO_ROOT / "corpus" / "seed").iterdir()):
            if not (process_dir / "claims").exists():
                continue
            ground_truth, mentions = self.mentions_for(process_dir)
            found = find_fractures(mentions)
            cast_size = len(ground_truth["cast"])
            assert len(found) < cast_size, (
                f"{process_dir.name}: {len(found)} fractures among {cast_size} people is noise"
            )

    @pytest.mark.xfail(
        reason="known recall limit: general contradiction detection needs a model checker. "
        "Here both accounts are incompatible but neither quantifies anything, so no "
        "deterministic comparison exists. Approximating it would tune a heuristic to this "
        "corpus rather than detect contradictions. Should pass once the checker lands.",
        strict=True,
    )
    def test_contradiction_shaped_plant_is_detected(self):
        _, involved = self.planted_fracture(
            REPO_ROOT / "corpus" / "seed" / "hospital-onboarding"
        )
        assert involved


class TestContradictionRequiresDisagreement:
    def test_reciprocal_collaboration_is_not_a_fracture(self):
        """Two people who both describe working together are collaborating, not fracturing."""
        assert find_fractures(
            {("a", "b"): [claim("handoff")], ("b", "a"): [claim("wait")]}
        ) == []

    def test_non_overlapping_durations_are_a_contradiction(self):
        def waited(low, high, unit):
            return {
                "kind": "wait", "verbatim": "x", "subject_scope": "self",
                "payload": {"waiting_on": "them", "owner": "internal",
                            "duration": {"low": low, "high": high, "unit": unit}},
            }

        found = find_fractures(
            {("a", "b"): [waited(3, 5, "day")], ("b", "a"): [waited(10, 20, "minute")]}
        )
        assert len(found) == 1 and found[0].kind == "contradiction"

    def test_overlapping_durations_are_not_a_contradiction(self):
        def waited(low, high):
            return {
                "kind": "wait", "verbatim": "x", "subject_scope": "self",
                "payload": {"waiting_on": "them", "owner": "internal",
                            "duration": {"low": low, "high": high, "unit": "day"}},
            }

        assert find_fractures({("a", "b"): [waited(2, 5)], ("b", "a"): [waited(4, 6)]}) == []

    def test_self_pairs_are_never_fractures(self):
        assert find_fractures({("rainer", "rainer"): [claim("wait")]}) == []
