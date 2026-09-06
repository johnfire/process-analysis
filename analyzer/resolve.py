"""Resolve mention strings to the entities they refer to.

Measured over the seed corpus, 88-91% of counterparty mentions appear in only one
respondent's account. The shared remainder is almost entirely first names. That asymmetry
splits resolution into jobs with very different difficulty, and only one of them needs a
model:

  people     - the cast is known, so this is a lookup, not a judgment. Code.
  steps      - some vocabulary overlap via handoff structure. Model, in v1 of this module.
  artifacts  - almost no string signal; two honest people name one document differently.
               Genuinely hard, and not required by v0's success criteria.

Anything that resolves to nothing is not an entity ("somebody", "an answer", "people").
Those are dropped by failing to resolve rather than by a stoplist, so the corpus never has
to be guessed at in advance.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Words that carry no identity even when they occupy a counterparty slot.
NON_IDENTIFYING = frozenset(
    {"somebody", "someone", "anybody", "anyone", "people", "they", "them",
     "everyone", "everybody", "nobody", "no one", "others", "someone else"}
)


@dataclass(frozen=True)
class Person:
    person_id: str
    name: str
    role: str


def fold(text: str) -> str:
    """Case, accent and punctuation insensitive form for matching names."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9 ]+", " ", stripped.lower()).strip()


def name_keys(person: Person) -> set[str]:
    """Every string that unambiguously denotes this person on its own."""
    folded = fold(person.name)
    parts = [part for part in folded.split() if len(part) > 2]
    keys = {folded, fold(person.person_id)}
    if parts:
        keys.add(parts[0])           # first name - how colleagues actually refer to each other
        keys.add(parts[-1])          # surname
    return {key for key in keys if key}


def build_person_index(cast: list[Person]) -> dict[str, str]:
    """Map every unambiguous name key to a person_id.

    A key claimed by two people is ambiguous and is deliberately excluded rather than
    resolved to whichever was seen first. Two colleagues called Petra must not be silently
    merged: merging distinct people fabricates agreement between accounts, which is the one
    error that would make a fracture disappear.
    """
    claimants: dict[str, set[str]] = {}
    for person in cast:
        for key in name_keys(person):
            claimants.setdefault(key, set()).add(person.person_id)
    return {key: next(iter(owners)) for key, owners in claimants.items() if len(owners) == 1}


def ambiguous_keys(cast: list[Person]) -> set[str]:
    """Name keys that more than one cast member answers to."""
    claimants: dict[str, set[str]] = {}
    for person in cast:
        for key in name_keys(person):
            claimants.setdefault(key, set()).add(person.person_id)
    return {key for key, owners in claimants.items() if len(owners) > 1}


def resolve_person(mention: str, person_index: dict[str, str]) -> str | None:
    """The person this mention denotes, or None if it denotes no known person.

    Matching is exact on a folded name key, plus a contained-word pass so that "Petra's
    side" and "ask Petra" resolve while "Petranet" does not.
    """
    folded = fold(mention)
    if not folded or folded in NON_IDENTIFYING:
        return None
    if folded in person_index:
        return person_index[folded]
    words = set(folded.split())
    matches = {person_index[key] for key in person_index if key in words}
    return next(iter(matches)) if len(matches) == 1 else None
