"""Extract claims from a transcript without letting names leave the server.

The pipeline: hide identifying text, ask a model (any callable that turns a prompt into text),
then rebuild each claim against the original transcript. A claim whose quotation cannot be found
in the text the model was shown is dropped, so a model cannot invent evidence. Identifiers that
belong to us (claim ids, respondent, session) are assigned here, never taken from the model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from analyzer.extract import CLAIM_SCHEMA, extract_json_array, render, validate_claims
from analyzer.pseudonymise import PersonToHide, Pseudonymised, original_quote, pseudonymise, restore_tokens

Complete = Callable[[str], str]


@dataclass(frozen=True)
class RespondentDetails:
    person_key: str
    name: str
    role: str
    person_index: int  # position in the cast; names the token that stands for this person


@dataclass(frozen=True)
class PrivateExtraction:
    claims: list[dict[str, Any]]
    ungrounded_count: int
    invalid: list[tuple[str, str]]  # (claim kind, why the schema refused it)

    @property
    def grounding_rate(self) -> float:
        attempted = len(self.claims) + self.ungrounded_count + len(self.invalid)
        return len(self.claims) / attempted if attempted else 1.0


def restore_in(value: Any, token_values: dict[str, str]) -> Any:
    """Replace tokens in every string nested inside a claim."""
    if isinstance(value, str):
        return restore_tokens(value, token_values)
    if isinstance(value, list):
        return [restore_in(item, token_values) for item in value]
    if isinstance(value, dict):
        return {key: restore_in(item, token_values) for key, item in value.items()}
    return value


def build_prompt(
    transcript_shown: str, respondent: RespondentDetails, role_shown: str, captured_at: str
) -> str:
    return render(
        "extract-claims.md",
        {
            "RESPONDENT_ID": "respondent",
            "RESPONDENT_NAME": f"PERSON_{respondent.person_index}",
            "RESPONDENT_ROLE": role_shown,
            "SESSION_ID": "session",
            "CAPTURED_AT": captured_at,
            "SCHEMA": CLAIM_SCHEMA.read_text(),
            "TRANSCRIPT": transcript_shown,
        },
    )


def rebuild_claim(
    candidate: dict[str, Any],
    original: str,
    shown: Pseudonymised,
    respondent: RespondentDetails,
    captured_at: str,
) -> dict[str, Any] | None:
    """The candidate rewritten against the original transcript, or None when its quote is not grounded."""
    quote = original_quote(original, shown, str(candidate.get("verbatim", "")))
    if quote is None:
        return None
    rebuilt = restore_in({k: v for k, v in candidate.items() if k != "verbatim"}, shown.token_values)
    rebuilt.update(
        verbatim=quote,
        respondent_id=respondent.person_key,
        session_id=f"s-{respondent.person_key}",
        captured_at=captured_at,
    )
    return rebuilt


def assign_ids(claims: list[tuple[str, dict[str, Any]]], person_key: str) -> list[dict[str, Any]]:
    """Sequential ids of our own, with `supersedes` pointers carried across to the new ids."""
    new_ids = {old: f"{person_key}-{number:03d}" for number, (old, _) in enumerate(claims, start=1)}
    finished = []
    for old, claim in claims:
        claim["id"] = new_ids[old]
        if claim.get("supersedes"):
            claim["supersedes"] = new_ids.get(claim["supersedes"])
        finished.append(claim)
    return finished


def extract_privately(
    complete: Complete,
    transcript: str,
    respondent: RespondentDetails,
    people: list[PersonToHide],
    extra_terms: list[str],
) -> PrivateExtraction:
    shown = pseudonymise(transcript, people, extra_terms)
    role_shown = pseudonymise(respondent.role, people, extra_terms).text
    captured_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = complete(build_prompt(shown.text, respondent, role_shown, captured_at))
    candidates = [c for c in extract_json_array(raw) if isinstance(c, dict)]
    kept: list[tuple[str, dict[str, Any]]] = []
    ungrounded = 0
    for number, candidate in enumerate(candidates):
        rebuilt = rebuild_claim(candidate, transcript, shown, respondent, captured_at)
        if rebuilt is None:
            ungrounded += 1
        else:
            kept.append((str(candidate.get("id", f"_{number}")), rebuilt))
    valid, refused = validate_claims(assign_ids(kept, respondent.person_key))
    return PrivateExtraction(valid, ungrounded, [(str(c.get("kind")), message) for c, message in refused])
