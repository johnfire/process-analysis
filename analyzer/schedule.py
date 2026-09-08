"""Attribute waiting to the cadence that causes it, not only to a person.

The queue-gap calculation assumes waiting is interpersonal: one account pairs against
another. Measured on the seed corpus that assumption holds in one process and fails in the
other. Where people wait on "the Thursday batch" or "the next availability run" there is no
counterparty, because a batch has no opinion - so the gap is not merely unmeasured, it is
undefined, and every delay in that process is invisible to the instrument.

This is constraint #1 from PHILOSOPHY.md, cost of attention producing batching. It needs its
own instrument rather than a better version of the person-based one.

The join is still cross-respondent, and still the same shape: one person declares a cadence
("I do them Thursdays"), another waits on it ("the Thursday batch"), and neither of them
holds the resulting delay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Tokens that actually denote a recurrence. A cadence without one of these carries no
# timing - "always", "as quickly as possible", "most of the week" - and matching on it would
# associate waits with nothing.
TEMPORAL_TOKENS = frozenset(
    {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "daily", "weekly", "monthly", "fortnightly", "quarterly",
        "morning", "afternoon", "evening", "overnight", "nightly",
        "batch", "block", "run", "round", "slot", "session", "cycle", "sweep", "intake",
    }
)
SHARED_DECLARER = "multiple"


@dataclass(frozen=True)
class Cadence:
    """A recurrence somebody declared running."""

    declared_by: str
    text: str
    tokens: frozenset[str]

    @property
    def label(self) -> str:
        return self.text


@dataclass
class ScheduleNode:
    """A cadence treated as a bottleneck in its own right."""

    cadence: Cadence
    attributed_queue: list = field(default_factory=list)
    waiters: set[str] = field(default_factory=set)


def distinctive_tokens(text: str) -> frozenset[str]:
    """Temporal tokens, singularised so 'batch' and 'batches' are one thing."""
    return frozenset(
        singular
        for word in re.findall(r"[a-z]+", (text or "").lower())
        if (singular := singularise(word)) in TEMPORAL_TOKENS
    )


def singularise(word: str) -> str:
    """'batches' -> 'batch', 'runs' -> 'run'. Only ever toward a known temporal token."""
    for suffix in ("es", "s"):
        if word.endswith(suffix) and word[: -len(suffix)] in TEMPORAL_TOKENS:
            return word[: -len(suffix)]
    return word


def collect_cadences(claims_by_person: dict[str, list[dict]]) -> list[Cadence]:
    """Every declared recurrence that carries real timing.

    Requires batching, because a cadence that does not accumulate work does not create a
    queue, and requires a temporal token, because otherwise there is nothing to match on.
    """
    cadences: list[Cadence] = []
    for person_id, claims in claims_by_person.items():
        for claim in claims:
            if claim.get("kind") != "schedule":
                continue
            payload = claim.get("payload", {})
            if payload.get("batching") is not True:
                continue
            text = payload.get("cadence") or ""
            tokens = distinctive_tokens(text)
            if tokens:
                cadences.append(Cadence(person_id, text.strip(), tokens))
    return cadences


def match_cadence(waiting_on: str, cadences: list[Cadence]) -> Cadence | None:
    """The cadence a wait refers to, or a shared pattern when several people share it.

    Scored by how many distinctive tokens are shared. A tie means two people genuinely run
    the same rhythm - two colleagues both batching on Thursdays is ordinary, not a data
    problem - so guessing which of them causes a given wait would attribute real delay to
    the wrong person.

    Refusing outright would instead discard the finding, and in a batch-driven process the
    finding is the whole analysis. So a tie collapses to the shared pattern: the delay is
    attributed to "Thursday" with no single owner, which is exactly what is known. Refuse to
    guess *who*; never lose *what*.
    """
    target = distinctive_tokens(waiting_on)
    if not target:
        return None
    scored = [
        (len(target & cadence.tokens), cadence)
        for cadence in cadences
        if target & cadence.tokens
    ]
    if not scored:
        return None
    best = max(overlap for overlap, _ in scored)
    leaders = [cadence for overlap, cadence in scored if overlap == best]
    if len({cadence.text.lower() for cadence in leaders}) == 1:
        return leaders[0]

    shared = frozenset.intersection(*(cadence.tokens for cadence in leaders)) & target
    if not shared:
        return None
    return Cadence(SHARED_DECLARER, " + ".join(sorted(shared)), shared)
