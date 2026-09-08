"""Batch-caused waiting has no counterparty, so it needs its own instrument."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from analyzer.schedule import (  # noqa: E402
    SHARED_DECLARER,
    Cadence,
    collect_cadences,
    distinctive_tokens,
    match_cadence,
)


def schedule_claim(person_unused: str, cadence: str, batching) -> dict:
    return {"kind": "schedule", "payload": {"cadence": cadence, "batching": batching}}


class TestCadenceCollection:
    def test_batching_cadence_with_real_timing_is_collected(self):
        found = collect_cadences({"marta": [schedule_claim("marta", "Thursdays", True)]})
        assert [one.text for one in found] == ["Thursdays"]

    def test_vacuous_cadence_is_rejected(self):
        """'always' and 'as quickly as possible' carry no timing to match on."""
        claims = {"petra": [schedule_claim("petra", text, True)
                            for text in ("always", "as quickly as possible", "immediately")]}
        assert collect_cadences(claims) == []

    def test_non_batching_cadence_is_rejected(self):
        """A rhythm that does not accumulate work does not create a queue."""
        assert collect_cadences({"jonas": [schedule_claim("jonas", "Fridays", False)]}) == []


class TestTokens:
    def test_plurals_singularise(self):
        assert distinctive_tokens("in batches") == distinctive_tokens("one batch")
        assert "run" in distinctive_tokens("the morning runs")

    def test_non_temporal_words_are_ignored(self):
        assert distinctive_tokens("as quickly as possible") == frozenset()


class TestMatching:
    THURSDAY = Cadence("marta", "Thursdays", distinctive_tokens("Thursdays"))
    MORNING = Cadence("jonas", "Friday morning sweep", distinctive_tokens("Friday morning sweep"))
    ALSO_THURSDAY = Cadence(
        "lukas", "Tuesdays and Thursdays", distinctive_tokens("Tuesdays and Thursdays")
    )

    def test_unambiguous_match_names_the_owner(self):
        matched = match_cadence("the Thursday batch", [self.THURSDAY, self.MORNING])
        assert matched is not None and matched.declared_by == "marta"

    def test_two_people_sharing_a_rhythm_collapses_to_the_pattern(self):
        """Two colleagues both batching on Thursdays is ordinary, not a data problem.

        Guessing which one causes a given wait would attribute real delay to the wrong
        person; refusing outright would discard the finding, which in a batch-driven
        process is the whole analysis. Refuse to guess who, never lose what.
        """
        matched = match_cadence("the Thursday batch", [self.THURSDAY, self.ALSO_THURSDAY])
        assert matched is not None
        assert matched.declared_by == SHARED_DECLARER
        assert matched.text == "thursday"

    def test_a_wait_with_no_timing_matches_nothing(self):
        assert match_cadence("Krankenkasse confirmation", [self.THURSDAY]) is None
        assert match_cadence("the fitness certificate", [self.THURSDAY]) is None

    def test_more_specific_overlap_wins(self):
        specific = Cadence("a", "Thursday morning batch",
                           distinctive_tokens("Thursday morning batch"))
        matched = match_cadence("the Thursday morning batch", [specific, self.THURSDAY])
        assert matched is not None and matched.declared_by == "a"


class TestAgainstCorpus:
    def test_batch_caused_delay_is_recovered_where_it_dominates(self):
        """On both corpora most queue time is batch-caused and had been invisible."""
        from analyzer import metrics as metrics_module
        from analyzer.graph import build_graph, claims_by_person_from
        from analyzer.resolve import Person, build_person_index

        for process_dir in sorted((REPO_ROOT / "corpus" / "seed").iterdir()):
            if not (process_dir / "claims").exists():
                continue
            ground_truth = json.loads((process_dir / "ground_truth.json").read_text())
            cast = [Person(m["person_id"], m["name"], m["role"]) for m in ground_truth["cast"]]
            claims, names = claims_by_person_from(process_dir)
            graph = build_graph(claims, names, build_person_index(cast))
            computed = metrics_module.compute(graph)
            assert computed.ranked_schedules(), (
                f"{process_dir.name}: no cadence recovered, "
                "yet most of this process's queue is batch-caused"
            )
