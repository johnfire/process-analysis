"""Locate where two accounts of the same working relationship fail to agree.

A fracture is not a data-quality problem to be cleaned up. It is the located point where
information is being lost between two people, and it is the highest-value observation the
method produces.

Fractures come in two forms, and the second is easy to miss:

  CONTRADICTION - both parties describe the relationship and describe it incompatibly.
                  A dispute: the channel works, the accounts differ.

  SILENCE       - one party describes an active, ongoing interaction with the other, and
                  the other's account contains no trace of them at all. The channel is not
                  disputed; it is not arriving.

Silence is the stronger evidence and the more common real-world shape. Both seed corpora
plant "a request the other team never received" - in one the parties still talk about each
other and it surfaces as contradiction, in the other the blamed party has genuinely never
heard of the sender. A detector built only for contradictions finds the first and is blind
to the second.

KNOWN RECALL LIMIT. Silence is structurally determinable and this module detects it. General
contradiction is not. Two accounts can be plainly incompatible while sharing no comparable
field: in the hospital corpus one party is waiting on the other, who says "she tells me
verbally" and "she'll say she's sent someone over, but I need the paperwork" - neither
quantifies anything, so nothing here can compare them. Non-overlapping durations are one
computable special case and are implemented. The general case requires semantically comparing
two accounts, which is a model's job (the checker placement in PHILOSOPHY.md) and is deferred
rather than approximated. Approximating it would mean tuning a heuristic until the corpus
passed, which measures the tuning rather than the method.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Claim kinds that assert a live channel between two people, rather than mere awareness of
# their existence. Naming a colleague in passing is not a relationship; waiting on them is.
INTERACTION_KINDS = frozenset({"wait", "handoff", "rework", "approval", "exception"})

# Units in minutes, for comparing durations two people give for the same relationship.
UNIT_MINUTES = {"minute": 1, "hour": 60, "day": 1440, "week": 10080, "month": 43200}


@dataclass(frozen=True)
class Fracture:
    kind: str  # "contradiction" | "silence"
    claimant: str
    counterparty: str
    claimant_claims: list[dict] = field(default_factory=list)
    counterparty_claims: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.kind == "silence":
            return (
                f"{self.claimant} describes an active dependency on {self.counterparty}; "
                f"{self.counterparty}'s account never mentions {self.claimant}"
            )
        return (
            f"{self.claimant} and {self.counterparty} both describe their shared work, "
            f"incompatibly"
        )


def asserts_interaction(claims: list[dict]) -> bool:
    """Whether these claims describe a live channel rather than passing awareness."""
    return any(claim.get("kind") in INTERACTION_KINDS for claim in claims)


def stated_ranges(claims: list[dict]) -> list[tuple[float, float]]:
    """Every duration either party puts on the shared relationship, in minutes."""
    ranges: list[tuple[float, float]] = []
    for one in claims:
        payload = one.get("payload", {})
        quantity = payload.get("value") if one.get("kind") == "duration" else payload.get("duration")
        if not isinstance(quantity, dict):
            continue
        scale = UNIT_MINUTES.get(quantity.get("unit"))
        if scale is None:
            continue
        low, high = quantity.get("low"), quantity.get("high")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            ranges.append((min(low, high) * scale, max(low, high) * scale))
    return ranges


def accounts_disagree(one_side: list[dict], other_side: list[dict]) -> bool:
    """Whether the two accounts actually conflict, rather than merely coexisting.

    Two colleagues who both describe working together are collaborating, not fracturing.
    Reporting every reciprocal pair as a contradiction flags everything, which is the same
    as flagging nothing. A contradiction needs evidence of real disagreement, and the one
    form measurable without a model is a pair of non-overlapping duration ranges for the
    same relationship.
    """
    left, right = stated_ranges(one_side), stated_ranges(other_side)
    if not left or not right:
        return False
    return all(
        low_a > high_b or low_b > high_a
        for low_a, high_a in left
        for low_b, high_b in right
    )


def find_fractures(mentions: dict[tuple[str, str], list[dict]]) -> list[Fracture]:
    """Find fractures from a map of (speaker, subject) -> the claims they made about them.

    Only pairs where at least one side asserts a live interaction are considered. Two people
    who simply never mention each other are not a fracture; they are colleagues who do not
    work together, and reporting that would bury the real findings in noise.
    """
    fractures: list[Fracture] = []
    seen_pairs: set[frozenset[str]] = set()

    for (speaker, subject), claims in sorted(mentions.items()):
        if speaker == subject:
            # Self-reference that survived alias filtering because it arrived inside a
            # phrase ("an answer from Rainer") and only resolved to a person afterwards.
            continue
        reciprocal = mentions.get((subject, speaker), [])

        if not reciprocal:
            if asserts_interaction(claims):
                fractures.append(Fracture("silence", speaker, subject, claims, []))
            continue

        pair = frozenset({speaker, subject})
        if pair in seen_pairs:
            continue
        if (asserts_interaction(claims) or asserts_interaction(reciprocal)) and accounts_disagree(
            claims, reciprocal
        ):
            seen_pairs.add(pair)
            fractures.append(
                Fracture("contradiction", speaker, subject, claims, reciprocal)
            )

    return fractures
