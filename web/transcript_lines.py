"""Finding where in a transcript a quoted sentence was said, so evidence can link to its source."""

from __future__ import annotations

import re
from dataclasses import dataclass

_QUOTE_TRANSLATION = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_BOLD = re.compile(r"\*\*(.+?)\*\*")
FALLBACK_PREFIX_CHARACTERS = 40


@dataclass(frozen=True)
class TranscriptLine:
    number: int
    text: str


def normalise(text: str) -> str:
    return " ".join(text.translate(_QUOTE_TRANSLATION).lower().split())


def transcript_lines(body: str) -> list[TranscriptLine]:
    """The non-empty lines of a transcript, keeping their line numbers in the file."""
    return [
        TranscriptLine(number, line) for number, line in enumerate(body.splitlines(), start=1) if line.strip()
    ]


def locate_quote(body: str, verbatim: str) -> int | None:
    """The line number holding this quote, or None. Typographic quotes and spacing are ignored."""
    wanted = normalise(verbatim)
    if not wanted:
        return None
    lines = [(line.number, normalise(line.text)) for line in transcript_lines(body)]
    for number, text in lines:
        if wanted in text:
            return number
    prefix = wanted[:FALLBACK_PREFIX_CHARACTERS]
    for number, text in lines:
        if len(prefix) >= FALLBACK_PREFIX_CHARACTERS and prefix in text:
            return number
    return None


def bold_markup_to_html(escaped_text: str) -> str:
    """Turn **speaker:** markers into <strong>. The input must already be HTML-escaped."""
    return _BOLD.sub(r"<strong>\1</strong>", escaped_text)
