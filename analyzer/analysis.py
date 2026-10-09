"""One analysis run over a process's claims: the shared core of the CLI and the web app.

Pure: claims in, findings out. Nothing here reads a file or a database, so the same function
serves a terminal, a CI scorer and a hosted viewer, and always gives the same answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from analyzer.fracture import Fracture, find_fractures
from analyzer.graph import build_graph
from analyzer.metrics import ProcessMetrics, compute
from analyzer.resolve import Person, build_person_index, resolve_person
from analyzer.triangulation import aliases_for, named_counterparties

ANALYZER_VERSION = "0.1.0"


@dataclass(frozen=True)
class ProcessAnalysis:
    metrics: ProcessMetrics
    fractures: list[Fracture]
    cast: list[Person]
    claim_count: int
    interview_count: int


def collect_mentions(
    claims_by_person: dict[str, list[dict]], names: dict[str, str], person_index: dict[str, str]
) -> dict[tuple[str, str], list[dict]]:
    """For each (speaker, subject) pair, the claims the speaker made that name the subject."""
    mentions: dict[tuple[str, str], list[dict]] = {}
    for speaker, speaker_claims in claims_by_person.items():
        speaker_aliases = aliases_for(speaker, names.get(speaker, speaker))
        for claim in speaker_claims:
            for mention in named_counterparties(claim, speaker_aliases):
                subject = resolve_person(mention, person_index)
                if subject and subject != speaker:
                    mentions.setdefault((speaker, subject), []).append(claim)
    return mentions


def analyse(cast: list[Person], claims_by_person: dict[str, list[dict]]) -> ProcessAnalysis:
    names = {member.person_id: member.name for member in cast}
    person_index = build_person_index(cast)
    graph = build_graph(claims_by_person, names, person_index)
    mentions = collect_mentions(claims_by_person, names, person_index)
    return ProcessAnalysis(
        metrics=compute(graph),
        fractures=find_fractures(mentions),
        cast=cast,
        claim_count=sum(len(claims) for claims in claims_by_person.values()),
        interview_count=len(claims_by_person),
    )
