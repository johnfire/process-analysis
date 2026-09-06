"""Generate a synthetic process corpus: hidden ground truth, then per-person testimony.

Two-stage, per docs/EVAL.md. An architect model invents the true process; cast models then
speak as individual employees who can each see only their own slice of it.

The information barrier is enforced here, in code, by constructing each slice and passing
nothing else. It is never delegated to an instruction asking a model to disregard what it
has already been shown.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CORPUS_ROOT = Path(__file__).resolve().parent
PROMPTS = CORPUS_ROOT / "prompts"
GROUND_TRUTH_SCHEMA = CORPUS_ROOT / "spec" / "ground-truth.schema.json"

# Fields a respondent could never know about their own step, and which would leak the answer key.
HIDDEN_STEP_FIELDS = frozenset({"true_classification", "position"})


@dataclass(frozen=True)
class ModelCall:
    """One invocation of an external model CLI."""

    label: str
    argv: tuple[str, ...]
    timeout_seconds: int = 900


ARCHITECT_MODEL = ModelCall("hermes/deepseek", ("hermes", "-z"))
CAST_MODEL = ModelCall("codex/gpt", ("codex", "exec", "--skip-git-repo-check"))


def run_model(call: ModelCall, prompt: str) -> str:
    """Invoke a model CLI with the prompt as its final argument."""
    completed = subprocess.run(
        [*call.argv, prompt],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=call.timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{call.label} exited {completed.returncode}: {completed.stderr[-2000:]}")
    return completed.stdout


def extract_json_object(raw_output: str) -> dict:
    """Pull the JSON object out of model output that may carry fences or chatter."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_output, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        opening = raw_output.find("{")
        closing = raw_output.rfind("}")
        if opening == -1 or closing <= opening:
            raise ValueError(f"no JSON object found in output:\n{raw_output[-2000:]}")
        candidate = raw_output[opening : closing + 1]
    return json.loads(candidate)


def render(template_name: str, substitutions: dict[str, str]) -> str:
    text = (PROMPTS / template_name).read_text()
    for placeholder, value in substitutions.items():
        text = text.replace("{{" + placeholder + "}}", value)
    remaining = re.findall(r"\{\{([A-Z_]+)\}\}", text)
    if remaining:
        raise ValueError(f"unfilled placeholders in {template_name}: {sorted(set(remaining))}")
    return text


def validate_ground_truth(ground_truth: dict) -> None:
    try:
        import jsonschema
    except ImportError:
        print("  ! jsonschema not installed - skipping validation", file=sys.stderr)
        return
    schema = json.loads(GROUND_TRUTH_SCHEMA.read_text())
    jsonschema.Draft202012Validator(schema).validate(ground_truth)


def build_slice(ground_truth: dict, person_id: str) -> dict:
    """Everything one person could plausibly know, and nothing else.

    They know their own steps in detail, that work arrives from somewhere and departs to
    somewhere, and who their colleagues are. They do not know anyone else's timings, the
    shape of the process end to end, or any part of the answer key.
    """
    steps_by_id = {step["step_id"]: step for step in ground_truth["steps"]}
    own_steps = [step for step in ground_truth["steps"] if step["performed_by"] == person_id]
    own_step_ids = {step["step_id"] for step in own_steps}

    visible_steps = [
        {key: value for key, value in step.items() if key not in HIDDEN_STEP_FIELDS}
        for step in own_steps
    ]

    # Adjacency is knowable: work visibly arrives and departs. Its cost elsewhere is not.
    arrives_from = [
        {
            "from_person": steps_by_id[step["step_id"]]["performed_by"],
            "artifact": step.get("artifact"),
            "mechanism": step.get("mechanism"),
        }
        for step in ground_truth["steps"]
        if step.get("hands_to") in own_step_ids and step["step_id"] not in own_step_ids
    ]
    departs_to = [
        {
            "to_person": steps_by_id[step["hands_to"]]["performed_by"],
            "artifact": step.get("artifact"),
            "mechanism": step.get("mechanism"),
        }
        for step in own_steps
        if step.get("hands_to") and step["hands_to"] not in own_step_ids
    ]

    false_blame = ground_truth["planted"]["false_blame"]
    believes_blocked_by = false_blame["blames"] if false_blame["claimed_by"] == person_id else None

    return {
        "organisation": ground_truth["organisation"],
        "colleagues": [
            {"name": member["name"], "role": member["role"]}
            for member in ground_truth["cast"]
            if member["person_id"] != person_id
        ],
        "your_steps": visible_steps,
        "work_arrives_from": arrives_from,
        "work_departs_to": departs_to,
        "you_believe_you_are_blocked_by": believes_blocked_by,
    }


def invent_ground_truth(domain: str, headcount: int, sector: str) -> dict:
    architect_prompt = render(
        "architect.md",
        {
            "DOMAIN": domain,
            "HEADCOUNT": str(headcount),
            "SECTOR": sector,
            "SCHEMA": GROUND_TRUTH_SCHEMA.read_text(),
        },
    )
    print(f"[architect] {ARCHITECT_MODEL.label} - inventing process ...")
    return extract_json_object(run_model(ARCHITECT_MODEL, architect_prompt))


def generate_process(
    domain: str,
    headcount: int,
    sector: str,
    output_root: Path,
    existing_ground_truth: Path | None = None,
) -> Path:
    if existing_ground_truth is not None:
        print(f"[architect] reusing {existing_ground_truth}")
        ground_truth = json.loads(existing_ground_truth.read_text())
    else:
        ground_truth = invent_ground_truth(domain, headcount, sector)
    validate_ground_truth(ground_truth)

    process_dir = output_root / ground_truth["process_id"]
    (process_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    (process_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2) + "\n")
    print(f"  ground truth: {len(ground_truth['steps'])} steps, {len(ground_truth['cast'])} people")

    questions = (PROMPTS / "questions.md").read_text()
    for member in ground_truth["cast"]:
        person_slice = build_slice(ground_truth, member["person_id"])
        if not person_slice["your_steps"]:
            print(f"  - {member['name']}: no steps, skipped")
            continue
        cast_prompt = render(
            "cast.md",
            {
                "PERSON_NAME": member["name"],
                "PERSON_ROLE": member["role"],
                "TENURE": str(member["tenure_years"]),
                "DISPOSITION": member["disposition"],
                "ANXIETY": member.get("job_security_anxiety", "low"),
                "SLICE": json.dumps(person_slice, indent=2),
                "QUESTIONS": questions,
            },
        )
        print(f"[cast] {CAST_MODEL.label} - {member['name']} ({member['role']}) ...")
        transcript = run_model(CAST_MODEL, cast_prompt)
        destination = process_dir / "transcripts" / f"{member['person_id']}.md"
        destination.write_text(transcript)
        print(f"  {destination.relative_to(output_root)}: {len(transcript.split())} words")

    return process_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default="", help="e.g. 'inbound lead to first contact'")
    parser.add_argument("--headcount", type=int, default=180)
    parser.add_argument("--sector", default="industrial equipment distribution")
    parser.add_argument("--out", type=Path, default=CORPUS_ROOT / "seed")
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=None,
        help="Reuse an existing answer key and re-run only the cast stage.",
    )
    arguments = parser.parse_args()

    process_dir = generate_process(
        arguments.domain,
        arguments.headcount,
        arguments.sector,
        arguments.out,
        arguments.ground_truth,
    )
    print(f"\nwrote {process_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
