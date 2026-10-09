"""Replace identifying text with opaque tokens before a transcript leaves the server, and map back.

Names, email addresses, telephone numbers, web addresses and any extra terms the operator lists
(the organisation's name, product names) become tokens such as PERSON_2 or EMAIL_1. The model
sees the tokens; the people, roles and relationships stay legible, the identities do not.

Mapping back has two parts. A quoted sentence is recovered from the *original* transcript by
offset, so it is character-exact whatever form of the name was spoken ("Petra", "Petra Lang",
"Dr. Lang"). Any other text field has its tokens replaced by the canonical value.

This reduces what is disclosed; it does not make a transcript anonymous. A name in a form nobody
listed, or a detail that identifies someone without naming them, passes through. `leftovers`
lists capitalised words that survived, as a prompt for a human to look, not as a guarantee.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

MINIMUM_ALIAS_LENGTH = 3
MINIMUM_PHONE_DIGITS = 8  # a range such as "100 - 200" must survive: durations are the evidence
TOKEN_PATTERN = re.compile(r"\b(?:PERSON|TERM|EMAIL|PHONE|URL)_\d+\b")
_EMAIL = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
_URL = r"(?:https?://|www\.)[^\s<>\"')]+"
_PHONE = r"\+?\d[\d ()/.-]{6,}\d"
_TITLES = ("dr.", "dr", "prof.", "prof", "herr", "frau", "mr.", "mrs.", "ms.", "mr", "mrs", "ms")
_ONE_FOR_ONE = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"})
_WORD = re.compile(r"[^\W\d_]{3,}")
_COMMON_CAPITALISED = frozenset(
    {
        *("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        *("January", "February", "March", "April", "May", "June", "July", "August"),
        *("September", "October", "November", "December", "Interviewer"),
        *("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
        *("Januar", "Februar", "März", "Juni", "Juli", "Oktober", "Dezember"),
    }
)


@dataclass(frozen=True)
class PersonToHide:
    """A person whose name must not leave the server, with the words that refer to them."""

    index: int
    full_name: str


@dataclass(frozen=True)
class Replacement:
    original_start: int
    original_end: int
    new_start: int
    new_end: int
    token: str


@dataclass(frozen=True)
class Pseudonymised:
    text: str
    replacements: list[Replacement]
    token_values: dict[str, str]
    leftovers: list[tuple[str, int]] = field(default_factory=list)


def aliases_of(full_name: str) -> list[str]:
    """Every way a person is likely to be referred to, longest first."""
    words = full_name.split()
    without_title = [w for w in words if w.lower() not in _TITLES]
    candidates = {full_name, " ".join(without_title), *without_title}
    if len(without_title) >= 2 and len(words) > len(without_title):
        candidates.add(f"{words[0]} {without_title[-1]}")
    usable = {c.strip() for c in candidates if len(c.strip()) >= MINIMUM_ALIAS_LENGTH}
    return sorted(usable, key=len, reverse=True)


def alias_tokens(people: list[PersonToHide], extra_terms: list[str]) -> dict[str, str]:
    """Lower-cased alias -> token, for everything that is spelled out rather than pattern-matched."""
    table: dict[str, str] = {}
    for person in people:
        for alias in aliases_of(person.full_name):
            table.setdefault(alias.lower(), f"PERSON_{person.index}")
    for number, term in enumerate(extra_terms, start=1):
        if len(term.strip()) >= MINIMUM_ALIAS_LENGTH:
            table.setdefault(term.strip().lower(), f"TERM_{number}")
    return table


def build_pattern(aliases: list[str]) -> re.Pattern[str]:
    spelled = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    parts = [f"(?P<email>{_EMAIL})", f"(?P<url>{_URL})", f"(?P<phone>{_PHONE})"]
    if spelled:
        parts.append(rf"(?<!\w)(?P<alias>{spelled})(?!\w)")
    return re.compile("|".join(parts), re.IGNORECASE)


def pseudonymise(
    text: str, people: list[PersonToHide], extra_terms: list[str] | None = None
) -> Pseudonymised:
    aliases = alias_tokens(people, extra_terms or [])
    terms = extra_terms or []
    canonical = {f"PERSON_{p.index}": p.full_name for p in people}
    canonical.update({f"TERM_{number}": term for number, term in enumerate(terms, start=1)})
    pattern = build_pattern(list(aliases))
    numbering: dict[tuple[str, str], str] = {}
    pieces: list[str] = []
    replacements: list[Replacement] = []
    cursor, written = 0, 0
    for match in pattern.finditer(text):
        kind = match.lastgroup or ""
        value = match.group(0)
        if kind == "phone" and sum(character.isdigit() for character in value) < MINIMUM_PHONE_DIGITS:
            continue
        token = (
            aliases[value.lower()] if kind == "alias" else numbered_token(kind, value, numbering, canonical)
        )
        pieces.append(text[cursor : match.start()])
        written += match.start() - cursor
        replacements.append(Replacement(match.start(), match.end(), written, written + len(token), token))
        pieces.append(token)
        written += len(token)
        cursor = match.end()
    pieces.append(text[cursor:])
    result = "".join(pieces)
    return Pseudonymised(result, replacements, canonical, find_leftovers(result))


def numbered_token(
    kind: str, value: str, numbering: dict[tuple[str, str], str], canonical: dict[str, str]
) -> str:
    """EMAIL_1, EMAIL_2 ... one token per distinct address, number and web address."""
    key = (kind, value.lower())
    if key not in numbering:
        count = sum(1 for existing_kind, _ in numbering if existing_kind == kind) + 1
        numbering[key] = f"{kind.upper()}_{count}"
        canonical[numbering[key]] = value
    return numbering[key]


def find_leftovers(text: str, limit: int = 40) -> list[tuple[str, int]]:
    """Capitalised words that are still present and never appear in lower case: possible names.

    A word that shows up in lower case somewhere ("the", "batch") is an ordinary word that happens
    to start a sentence; one that is only ever capitalised ("Brigitte") might be a name nobody
    listed. German nouns are always capitalised, so this over-reports there. It is a prompt for a
    human to look, not a guarantee.
    """
    words = _WORD.findall(text)
    lower_case_forms = {word for word in words if word.islower()}
    counts: dict[str, int] = {}
    for word in words:
        is_capitalised = word[0].isupper() and word[1:].islower()
        if is_capitalised and word.lower() not in lower_case_forms and word not in _COMMON_CAPITALISED:
            counts[word] = counts.get(word, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def restore_tokens(text: str, token_values: dict[str, str]) -> str:
    """Put canonical values back in place of tokens; a token the model invented is left as written."""
    return TOKEN_PATTERN.sub(lambda match: token_values.get(match.group(0), match.group(0)), text)


def original_offset(replacements: list[Replacement], new_offset: int, is_end: bool) -> int:
    """Where an offset in the pseudonymised text falls in the original. Inside a token it snaps outward."""
    starts = [r.new_start for r in replacements]
    position = bisect_right(starts, new_offset) - 1
    if position < 0:
        return new_offset
    replacement = replacements[position]
    if new_offset < replacement.new_end:
        return replacement.original_end if is_end else replacement.original_start
    return replacement.original_end + (new_offset - replacement.new_end)


def compact_with_map(text: str) -> tuple[str, list[int]]:
    """Lower-cased text with typographic marks flattened and whitespace runs collapsed to one space.

    Returns the compact text and, for each of its characters, the index it came from. The
    flattening is one-for-one, so indexes in the compact text can be traced back exactly.
    """
    flattened = text.translate(_ONE_FOR_ONE).lower()
    characters: list[str] = []
    origins: list[int] = []
    previous_was_space = True
    for index, character in enumerate(flattened):
        is_space = character.isspace()
        if is_space and previous_was_space:
            continue
        previous_was_space = is_space
        characters.append(" " if is_space else character)
        origins.append(index)
    return "".join(characters), origins


def original_quote(original: str, pseudonymised: Pseudonymised, quoted: str) -> str | None:
    """The exact original wording of a quote the model took from the pseudonymised text, or None.

    Matching tolerates typographic punctuation, letter case and differences in spacing or line
    breaks, nothing else. A quote that is not in the text it was shown is not grounded and is
    refused.
    """
    shown = pseudonymised.text
    if len(shown.lower()) != len(shown):
        return None
    haystack, origins = compact_with_map(shown)
    needle = compact_with_map(quoted)[0].strip()
    found = haystack.find(needle) if needle else -1
    if found == -1:
        return None
    start = original_offset(pseudonymised.replacements, origins[found], is_end=False)
    end = original_offset(pseudonymised.replacements, origins[found + len(needle) - 1] + 1, is_end=True)
    return original[start:end]
