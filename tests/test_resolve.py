"""Person resolution is a lookup against a known cast, not a judgment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analyzer.resolve import (  # noqa: E402
    Person,
    ambiguous_keys,
    build_person_index,
    resolve_person,
)

CAST = [
    Person("rainer", "Rainer Hoffmann", "Regional Sales Manager"),
    Person("petra", "Petra Lindqvist", "Materials & Availability Planner"),
    Person("marta", "Marta Falck", "Quotation & Pricing"),
]
INDEX = build_person_index(CAST)


class TestResolution:
    def test_first_name_resolves(self):
        assert resolve_person("Petra", INDEX) == "petra"

    def test_full_name_resolves(self):
        assert resolve_person("Petra Lindqvist", INDEX) == "petra"

    def test_possessive_and_surrounding_words_resolve(self):
        assert resolve_person("Petra's side", INDEX) == "petra"
        assert resolve_person("ask Marta about it", INDEX) == "marta"

    def test_accents_and_case_are_folded(self):
        assert resolve_person("PETRA LINDQVIST", INDEX) == "petra"

    def test_substring_of_a_longer_word_does_not_resolve(self):
        """'Petranet' is a system, not Petra."""
        assert resolve_person("Petranet", INDEX) is None

    def test_non_identifying_words_resolve_to_nobody(self):
        for vague in ("somebody", "people", "someone else", "nobody"):
            assert resolve_person(vague, INDEX) is None

    def test_things_resolve_to_nobody(self):
        """88% of mentions are singletons like these; they must fail, not guess."""
        for thing in ("an answer", "availability information", "the morning run"):
            assert resolve_person(thing, INDEX) is None

    def test_two_named_people_in_one_mention_is_not_resolved(self):
        assert resolve_person("Petra and Marta", INDEX) is None


class TestAmbiguity:
    CLASHING = [
        Person("petra-l", "Petra Lindqvist", "Planner"),
        Person("petra-w", "Petra Weber", "Nurse"),
    ]

    def test_shared_first_name_is_excluded_not_guessed(self):
        """Merging two people fabricates agreement, which makes a fracture disappear."""
        index = build_person_index(self.CLASHING)
        assert resolve_person("Petra", index) is None
        assert "petra" in ambiguous_keys(self.CLASHING)

    def test_full_names_still_resolve_when_first_names_clash(self):
        index = build_person_index(self.CLASHING)
        assert resolve_person("Petra Lindqvist", index) == "petra-l"
        assert resolve_person("Petra Weber", index) == "petra-w"


class TestAgainstCorpus:
    def test_every_seed_cast_has_unambiguous_members(self):
        for ground_truth_path in sorted(Path(REPO_ROOT / "corpus" / "seed").glob("*/ground_truth.json")):
            ground_truth = json.loads(ground_truth_path.read_text())
            cast = [
                Person(member["person_id"], member["name"], member["role"])
                for member in ground_truth["cast"]
            ]
            index = build_person_index(cast)
            resolved = {resolve_person(member.name, index) for member in cast}
            assert None not in resolved, f"{ground_truth_path.parent.name}: a cast member is unresolvable"
            assert len(resolved) == len(cast), f"{ground_truth_path.parent.name}: cast members collide"
