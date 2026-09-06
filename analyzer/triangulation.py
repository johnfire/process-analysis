"""Decide, structurally, which claims are assertions about other people.

A claim like "I'm waiting on Petra" carries two things at once: that the respondent is
waiting, which they know directly, and that Petra is the cause, which they are inferring.
`subject_scope` is a single label over the whole claim and cannot express that, so an
extractor marking it `self` is not wrong - it is answering an ambiguous question.

Triangulation therefore does not depend on `subject_scope`. It derives from whether the
payload names somebody other than the respondent, which is a rule rather than a judgment,
and so belongs in code. `subject_scope` remains a useful signal about the respondent's own
epistemic stance; it is simply not what the fracture detector keys off.
"""

from __future__ import annotations

# Payload fields that name a party other than the claim's author.
COUNTERPARTY_FIELDS = (
    "waiting_on",
    "from",
    "to",
    "approver",
    "returned_by",
    "performed_by",
    "pulls_in",
    "borne_by",
    "blames",
    "target",
)


def named_counterparties(claim: dict, respondent_aliases: frozenset[str]) -> list[str]:
    """Candidate other-party mentions this claim makes an assertion about.

    These are candidates, not resolved actors. A `waiting_on` value is as likely to be a
    thing ("an answer", "availability information") as a person, and telling them apart is
    entity resolution's job, not this module's. Returning candidates and letting the
    resolver filter keeps the layers honest; guessing here would bury an unreviewable
    judgment inside a function whose whole point is being a rule rather than a judgment.
    """
    payload = claim.get("payload", {})
    found: list[str] = []
    for field in COUNTERPARTY_FIELDS:
        value = payload.get(field)
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate.strip():
                continue
            if candidate.strip().lower() in respondent_aliases:
                continue
            found.append(candidate.strip())
    for mention in claim.get("entity_refs", []):
        text = mention.get("text", "").strip()
        if mention.get("type") in {"actor", "team", "external_party"} and text:
            if text.lower() not in respondent_aliases:
                found.append(text)
    return sorted(set(found), key=str.lower)


def is_hypothesis_about_another(claim: dict, respondent_aliases: frozenset[str]) -> bool:
    """True when the claim asserts something about somebody other than its author.

    Such a claim is never scored as fact. It is promoted to a finding only when the named
    party's own account agrees, and recorded as a fracture when it does not.
    """
    return bool(named_counterparties(claim, respondent_aliases))


def aliases_for(person_id: str, name: str) -> frozenset[str]:
    """The strings a respondent might be called by, for excluding self-reference."""
    parts = {person_id.lower(), name.lower()}
    parts.update(fragment.lower() for fragment in name.split() if len(fragment) > 2)
    parts.update({"me", "i", "myself", "my"})
    return frozenset(parts)
