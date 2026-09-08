"""Extract typed claims from an interview transcript.

The first stage of the analyzer and the first place the model under test appears. Output is
validated twice: against the claim schema, and against the transcript itself — every claim
must quote a span that genuinely occurs in what the respondent said. A claim whose verbatim
cannot be found is discarded, because an ungrounded quotation is the one failure that would
make the whole evidence graph unfalsifiable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS = Path(__file__).resolve().parent / "prompts"
CLAIM_SCHEMA = REPO_ROOT / "schema" / "claim.schema.json"

# Transports. `claude -p` is deliberately absent: it does not invoke a model but starts an agent
# session inheriting the operator's global CLAUDE.md, hooks and skills. On the first extraction
# run a Stop hook fired inside the subprocess and its message was returned as the result; all
# fourteen calls failed identically. `--bare` skips hooks but disables the credential helper, and
# `--settings '{"hooks":{}}'` does not suppress global hooks. Beyond being broken it is the wrong
# shape - output would depend on the operator's local configuration, so a hook change on one
# machine could silently move eval scores.
TRANSPORTS = {
    # Unblocks the pipeline today. NOT independent: DeepSeek is also the corpus architect, so a
    # run on a DeepSeek-authored process shares blind spots with its own ground truth and any
    # resulting number is an upper bound, not a score. Adequate for a smoke test, which asks
    # whether extraction works at all rather than how well it does.
    "hermes": ("hermes", "-z"),
    # An independent analyzer. codex is a different model family from both the corpus
    # architect (DeepSeek) and from Claude, so a score from this transport is a measurement
    # rather than an upper bound - see docs/EVAL.md on correlated failure.
    "codex": ("codex", "exec", "--skip-git-repo-check"),
}
DEFAULT_TRANSPORT = "hermes"
ANALYZER_TIMEOUT_SECONDS = 1800

# Speech is transcribed with typographic punctuation; quoting it back through a model
# routinely swaps these. Normalising before comparison tests grounding, not encoding.
PUNCTUATION_EQUIVALENCE = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", " ": " "}


@dataclass(frozen=True)
class Respondent:
    respondent_id: str
    name: str
    role: str


@dataclass(frozen=True)
class ExtractionResult:
    claims: list[dict]
    discarded_ungrounded: list[dict]
    discarded_invalid: list[tuple[dict, str]]

    @property
    def grounding_rate(self) -> float:
        attempted = len(self.claims) + len(self.discarded_ungrounded)
        return len(self.claims) / attempted if attempted else 1.0


def normalise(text: str) -> str:
    for fancy, plain in PUNCTUATION_EQUIVALENCE.items():
        text = text.replace(fancy, plain)
    return " ".join(text.split()).lower()


def is_grounded(verbatim: str, transcript: str) -> bool:
    """A claim may only quote words the respondent actually said."""
    return normalise(verbatim) in normalise(transcript)


def render(template_name: str, substitutions: dict[str, str]) -> str:
    text = (PROMPTS / template_name).read_text()
    for placeholder, value in substitutions.items():
        text = text.replace("{{" + placeholder + "}}", value)
    unfilled = re.findall(r"\{\{([A-Z_]+)\}\}", text)
    if unfilled:
        raise ValueError(f"unfilled placeholders: {sorted(set(unfilled))}")
    return text


def extract_json_array(raw_output: str) -> list[dict]:
    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw_output, re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1))
    opening = raw_output.find("[")
    closing = raw_output.rfind("]")
    if opening == -1 or closing <= opening:
        raise ValueError(f"no JSON array in output:\n{raw_output[-2000:]}")
    return json.loads(raw_output[opening : closing + 1])


def run_analyzer(prompt: str, transport: str = DEFAULT_TRANSPORT) -> str:
    if transport not in TRANSPORTS:
        raise ValueError(f"unknown transport {transport!r}; have {sorted(TRANSPORTS)}")
    completed = subprocess.run(
        [*TRANSPORTS[transport], prompt],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=ANALYZER_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"analyzer exited {completed.returncode}: {completed.stderr[-2000:]}")
    return completed.stdout


def validate_claims(candidates: list[dict]) -> tuple[list[dict], list[tuple[dict, str]]]:
    try:
        import jsonschema
    except ImportError:
        print("  ! jsonschema not installed - skipping schema validation", file=sys.stderr)
        return candidates, []
    validator = jsonschema.Draft202012Validator(json.loads(CLAIM_SCHEMA.read_text()))
    valid: list[dict] = []
    invalid: list[tuple[dict, str]] = []
    for candidate in candidates:
        errors = sorted(validator.iter_errors(candidate), key=lambda error: error.path)
        if errors:
            invalid.append((candidate, errors[0].message))
        else:
            valid.append(candidate)
    return valid, invalid


def extract_from_transcript(
    transcript: str,
    respondent: Respondent,
    session_id: str,
    transport: str = DEFAULT_TRANSPORT,
) -> ExtractionResult:
    prompt = render(
        "extract-claims.md",
        {
            "RESPONDENT_ID": respondent.respondent_id,
            "RESPONDENT_NAME": respondent.name,
            "RESPONDENT_ROLE": respondent.role,
            "SESSION_ID": session_id,
            "CAPTURED_AT": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "SCHEMA": CLAIM_SCHEMA.read_text(),
            "TRANSCRIPT": transcript,
        },
    )
    candidates = extract_json_array(run_analyzer(prompt, transport))
    grounded = [claim for claim in candidates if is_grounded(claim.get("verbatim", ""), transcript)]
    ungrounded = [claim for claim in candidates if claim not in grounded]
    valid, invalid = validate_claims(grounded)
    return ExtractionResult(valid, ungrounded, invalid)


def claims_dirname(transport: str) -> str:
    """Each analyzer writes its own claims, so two transports can be compared."""
    return "claims" if transport == DEFAULT_TRANSPORT else f"claims-{transport}"


def extract_process(process_dir: Path, transport: str = DEFAULT_TRANSPORT) -> Path:
    """Extract claims for every respondent in one generated process."""
    ground_truth = json.loads((process_dir / "ground_truth.json").read_text())
    cast_by_id = {member["person_id"]: member for member in ground_truth["cast"]}
    claims_dir = process_dir / claims_dirname(transport)
    claims_dir.mkdir(exist_ok=True)

    for transcript_path in sorted((process_dir / "transcripts").glob("*.md")):
        person_id = transcript_path.stem
        member = cast_by_id.get(person_id)
        if member is None:
            print(f"  ! {person_id} not in cast, skipped", file=sys.stderr)
            continue
        respondent = Respondent(person_id, member["name"], member["role"])
        print(f"[extract] {member['name']} ...")
        result = extract_from_transcript(
            transcript_path.read_text(), respondent, f"s-{person_id}", transport
        )
        (claims_dir / f"{person_id}.json").write_text(json.dumps(result.claims, indent=2) + "\n")
        print(
            f"  {len(result.claims)} claims"
            f" | grounding {result.grounding_rate:.0%}"
            f" | {len(result.discarded_ungrounded)} ungrounded"
            f" | {len(result.discarded_invalid)} schema-invalid"
        )
        for candidate, message in result.discarded_invalid[:3]:
            print(f"    invalid ({candidate.get('kind')}): {message[:120]}", file=sys.stderr)
    return claims_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("process_dir", type=Path, help="corpus/seed/<process-id>")
    parser.add_argument("--transport", default=DEFAULT_TRANSPORT, choices=sorted(TRANSPORTS))
    arguments = parser.parse_args()
    claims_dir = extract_process(arguments.process_dir, arguments.transport)
    print(f"\nwrote {claims_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
