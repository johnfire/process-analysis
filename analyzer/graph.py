"""Build a process graph from claims and resolutions.

The graph is derived, never authored: a pure function of claims plus person resolution, so
regenerating after a correction costs nothing and every node can name who said what.

Nodes are people and edges are handoffs between them. Steps are not yet nodes because step
resolution needs a model and is v1 work - but this is also the right shape for v0 on its own
terms, because the queue-gap calculation is about pairs of people. Two people hold the two
halves of a number neither can see alone; that is a property of the people, not the steps.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from analyzer.resolve import resolve_person
from analyzer.triangulation import aliases_for, named_counterparties

UNIT_MINUTES = {"minute": 1, "hour": 60, "day": 1440, "week": 10080, "month": 43200}


@dataclass(frozen=True)
class Interval:
    """A duration the respondent gave as a range, because that is how people speak."""

    low: float
    high: float

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2


def to_interval(quantity: dict | None) -> Interval | None:
    if not isinstance(quantity, dict):
        return None
    scale = UNIT_MINUTES.get(quantity.get("unit"))
    low, high = quantity.get("low"), quantity.get("high")
    if scale is None or not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        return None
    return Interval(min(low, high) * scale, max(low, high) * scale)


@dataclass
class PersonNode:
    person_id: str
    touch: list[Interval] = field(default_factory=list)
    queue_self_reported: list[Interval] = field(default_factory=list)
    waits_internal: list[Interval] = field(default_factory=list)
    waits_external: list[Interval] = field(default_factory=list)
    complaints: int = 0
    claims: int = 0


@dataclass
class HandoffEdge:
    source: str
    target: str
    mechanisms: set[str] = field(default_factory=set)
    chased: bool = False
    # Queue the source attributes to waiting on the target. Half of a queue gap.
    attributed_queue: list[Interval] = field(default_factory=list)
    supporting_claims: int = 0


@dataclass
class ProcessGraph:
    nodes: dict[str, PersonNode] = field(default_factory=dict)
    edges: dict[tuple[str, str], HandoffEdge] = field(default_factory=dict)
    unresolved_mentions: int = 0

    def node(self, person_id: str) -> PersonNode:
        return self.nodes.setdefault(person_id, PersonNode(person_id))

    def edge(self, source: str, target: str) -> HandoffEdge:
        return self.edges.setdefault((source, target), HandoffEdge(source, target))


def durations_by_answer(claims: list[dict]) -> dict[str, list[Interval]]:
    """Group every duration a respondent gave, by the answer it came from.

    People name who they are waiting on and how long they wait in separate sentences, so
    those arrive as separate claims and the wait claim's own `duration` is usually null.
    Measured on the seed corpus, not one wait claim in either process carried both a
    resolvable person and a duration - which silently reduced the bottleneck ranking to
    noise until it was caught.

    `question_id` is the association: claims extracted from one answer share it, and one
    answer is one thought about one thing.
    """
    grouped: dict[str, list[Interval]] = {}
    for claim in claims:
        question = claim.get("question_id")
        if not question:
            continue
        payload = claim.get("payload", {})
        quantity = payload.get("value") if claim.get("kind") == "duration" else payload.get("duration")
        interval = to_interval(quantity)
        if interval is not None:
            grouped.setdefault(question, []).append(interval)
    return grouped


def build_graph(
    claims_by_person: dict[str, list[dict]],
    cast_names: dict[str, str],
    person_index: dict[str, str],
) -> ProcessGraph:
    """Derive the graph. Deterministic given the same claims and resolutions."""
    graph = ProcessGraph()
    for person_id in claims_by_person:
        graph.node(person_id)

    for person_id, claims in claims_by_person.items():
        speaker = graph.node(person_id)
        speaker_aliases = aliases_for(person_id, cast_names.get(person_id, person_id))
        answer_durations = durations_by_answer(claims)

        for claim in claims:
            speaker.claims += 1
            kind, payload = claim.get("kind"), claim.get("payload", {})

            if kind == "complaint":
                speaker.complaints += 1

            if kind == "duration":
                interval = to_interval(payload.get("value"))
                if interval is not None:
                    if payload.get("measure") == "touch":
                        speaker.touch.append(interval)
                    elif payload.get("measure") == "queue":
                        speaker.queue_self_reported.append(interval)

            if kind == "wait":
                owner = payload.get("owner")
                stated = to_interval(payload.get("duration"))
                # Fall back to whatever duration the same answer carried, since the length
                # of a wait is usually stated in a different sentence from its target.
                intervals = (
                    [stated]
                    if stated is not None
                    else answer_durations.get(claim.get("question_id") or "", [])
                )
                for interval in intervals:
                    if owner == "external":
                        speaker.waits_external.append(interval)
                    else:
                        speaker.waits_internal.append(interval)

            targets = {
                resolved
                for mention in named_counterparties(claim, speaker_aliases)
                if (resolved := resolve_person(mention, person_index)) and resolved != person_id
            }
            if not targets:
                graph.unresolved_mentions += 1
                continue

            for target in targets:
                edge = graph.edge(person_id, target)
                edge.supporting_claims += 1
                if kind == "handoff":
                    mechanism = payload.get("mechanism")
                    if mechanism:
                        edge.mechanisms.add(mechanism)
                    if payload.get("chased"):
                        edge.chased = True
                if kind == "wait":
                    stated = to_interval(payload.get("duration"))
                    edge.attributed_queue.extend(
                        [stated]
                        if stated is not None
                        else answer_durations.get(claim.get("question_id") or "", [])
                    )

    return graph


def claims_by_person_from(process_dir) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Load one generated process's claims, keyed by respondent."""
    import json
    from pathlib import Path

    process_dir = Path(process_dir)
    ground_truth = json.loads((process_dir / "ground_truth.json").read_text())
    names = {member["person_id"]: member["name"] for member in ground_truth["cast"]}
    claims = {
        path.stem: json.loads(path.read_text())
        for path in sorted((process_dir / "claims").glob("*.json"))
    }
    return claims, names
