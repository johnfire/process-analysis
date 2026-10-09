"""What a provider would be sent, shown to the operator before anything is sent. Pure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from analyzer.pseudonymise import PersonToHide, pseudonymise

SAMPLE_CHARACTERS = 1500
CHARACTERS_PER_TOKEN = 3.5  # a rough rule for English and German prose
PROMPT_OVERHEAD_TOKENS = 3000  # the instructions and claim schema sent with every transcript
OUTPUT_TO_INPUT_RATIO = 0.4


@dataclass(frozen=True)
class Preview:
    sample: str
    replacement_count: int
    leftovers: list[tuple[str, int]]
    estimated_tokens_in: int
    estimated_tokens_out: int

    @property
    def estimated_total(self) -> int:
        return self.estimated_tokens_in + self.estimated_tokens_out


def people_from_cast(cast: list[dict[str, Any]]) -> list[PersonToHide]:
    return [PersonToHide(position, member["name"]) for position, member in enumerate(cast, start=1)]


def estimate_tokens(transcripts: list[str]) -> tuple[int, int]:
    """A rough (in, out) token estimate for extracting every transcript. Only a guide for the cap."""
    tokens_in = sum(int(len(text) / CHARACTERS_PER_TOKEN) + PROMPT_OVERHEAD_TOKENS for text in transcripts)
    return tokens_in, int(tokens_in * OUTPUT_TO_INPUT_RATIO)


def build_preview(
    cast: list[dict[str, Any]], transcripts: dict[str, str], terms: list[str]
) -> Preview | None:
    """The first transcript as a provider would see it, and any words left that might identify someone."""
    if not transcripts:
        return None
    people = people_from_cast(cast)
    first = next((m["person_id"] for m in cast if m["person_id"] in transcripts), next(iter(transcripts)))
    shown = pseudonymise(transcripts[first], people, terms)
    all_hidden = [pseudonymise(text, people, terms) for text in transcripts.values()]
    leftovers: dict[str, int] = {}
    for one in all_hidden:
        for word, count in one.leftovers:
            leftovers[word] = leftovers.get(word, 0) + count
    tokens_in, tokens_out = estimate_tokens(list(transcripts.values()))
    return Preview(
        sample=shown.text[:SAMPLE_CHARACTERS],
        replacement_count=sum(len(one.replacements) for one in all_hidden),
        leftovers=sorted(leftovers.items(), key=lambda item: (-item[1], item[0]))[:40],
        estimated_tokens_in=tokens_in,
        estimated_tokens_out=tokens_out,
    )
