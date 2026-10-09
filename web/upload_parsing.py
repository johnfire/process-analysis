"""Turning the process-creation form into validated respondents. Pure: no request, no database."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_ROWS = 20
MAX_TRANSCRIPT_CHARACTERS = 300_000
MAX_TERMS = 50
MAX_TERM_CHARACTERS = 100
MAX_NAME_CHARACTERS = 120
MAX_ROLE_CHARACTERS = 200


@dataclass(frozen=True)
class Respondent:
    person_key: str
    name: str
    role: str
    transcript: str


@dataclass(frozen=True)
class ParsedUpload:
    respondents: list[Respondent]
    errors: list[str]


def slugify(name: str) -> str:
    """A stable lower-case key from a name: 'Dr. Elena Vidal' -> 'dr-elena-vidal'."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-") or "respondent"


def unique_key(base: str, taken: set[str]) -> str:
    candidate, number = base, 2
    while candidate in taken:
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def decode_upload(raw: bytes) -> str | None:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def parse_terms(raw: str) -> tuple[list[str], list[str]]:
    """Extra words to hide, one per line: (terms, errors)."""
    terms: list[str] = []
    for line in raw.splitlines():
        term = line.strip()
        if term and term.lower() not in {t.lower() for t in terms}:
            terms.append(term)
    errors = []
    if len(terms) > MAX_TERMS:
        errors.append(f"List at most {MAX_TERMS} extra terms to hide.")
    if any(len(term) > MAX_TERM_CHARACTERS for term in terms):
        errors.append(f"Each term to hide must be under {MAX_TERM_CHARACTERS} characters.")
    return terms[:MAX_TERMS], errors


def row_text(form: Mapping[str, Any], uploaded: Mapping[int, bytes], row: int) -> tuple[str, str | None]:
    """The transcript for a row: an uploaded file wins over pasted text. (text, error)"""
    if uploaded.get(row):
        decoded = decode_upload(uploaded[row])
        if decoded is None:
            return "", f"Row {row + 1}: the file is not UTF-8 text. Save it as plain text or Markdown."
        return decoded.strip(), None
    return str(form.get(f"text_{row}", "")).strip(), None


def validate_row(row: int, name: str, role: str, transcript: str) -> list[str]:
    problems = []
    if not name:
        problems.append(f"Row {row + 1}: enter the respondent's name.")
    if not role:
        problems.append(f"Row {row + 1}: enter their role.")
    if len(name) > MAX_NAME_CHARACTERS or len(role) > MAX_ROLE_CHARACTERS:
        problems.append(f"Row {row + 1}: the name or role is too long.")
    if len(transcript) > MAX_TRANSCRIPT_CHARACTERS:
        problems.append(
            f"Row {row + 1}: the transcript is longer than {MAX_TRANSCRIPT_CHARACTERS:,} characters."
        )
    return problems


def parse_respondents(form: Mapping[str, Any], uploaded: Mapping[int, bytes]) -> ParsedUpload:
    """Rows with no transcript are ignored; every other row must be complete."""
    respondents: list[Respondent] = []
    errors: list[str] = []
    taken: set[str] = set()
    for row in range(MAX_ROWS):
        name, role = str(form.get(f"name_{row}", "")).strip(), str(form.get(f"role_{row}", "")).strip()
        transcript, problem = row_text(form, uploaded, row)
        if problem:
            errors.append(problem)
            continue
        if not transcript and not name and not role:
            continue
        if not transcript:
            errors.append(f"Row {row + 1}: paste or upload the transcript.")
            continue
        row_problems = validate_row(row, name, role, transcript)
        errors.extend(row_problems)
        if not row_problems:
            key = unique_key(slugify(name), taken)
            taken.add(key)
            respondents.append(Respondent(key, name, role, transcript))
    if not respondents and not errors:
        errors.append("Add at least one interview transcript.")
    return ParsedUpload(respondents, errors)
