"""Command line entry point: run the analyzer over a process and print what it found.

Usage:
    python -m analyzer report corpus/seed/hospital-onboarding
    python -m analyzer score  corpus/seed/hospital-onboarding
    python -m analyzer list
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyzer import metrics as metrics_module
from analyzer.fracture import find_fractures
from analyzer.graph import build_graph, claims_by_person_from
from analyzer.resolve import Person, build_person_index, resolve_person
from analyzer.score import score
from analyzer.triangulation import aliases_for, named_counterparties

CORPUS_ROOT = Path(__file__).resolve().parents[1] / "corpus" / "seed"
BAR_WIDTH = 62


def find_process(reference: str) -> Path:
    """Resolve a process by path, exact name, or unambiguous prefix.

    Typing the full corpus path every time is the friction that stops a tool being used, so
    `report hospital` resolves to corpus/seed/hospital-onboarding. An ambiguous abbreviation
    lists the candidates rather than picking one.
    """
    candidate = Path(reference)
    if candidate.exists():
        return candidate
    if (CORPUS_ROOT / reference).exists():
        return CORPUS_ROOT / reference
    available = sorted(path for path in CORPUS_ROOT.iterdir() if path.is_dir())
    matches = [path for path in available if path.name.startswith(reference)]
    if not matches:
        matches = [path for path in available if reference.lower() in path.name.lower()]
    if len(matches) == 1:
        return matches[0]
    names = ", ".join(path.name for path in (matches or available))
    problem = "ambiguous" if matches else "no such process"
    raise SystemExit(f"{problem}: {reference!r}\n  available: {names}")


def load(process_dir: Path):
    ground_truth = json.loads((process_dir / "ground_truth.json").read_text())
    cast = [
        Person(member["person_id"], member["name"], member["role"])
        for member in ground_truth["cast"]
    ]
    index = build_person_index(cast)
    claims, names = claims_by_person_from(process_dir)
    graph = build_graph(claims, names, index)
    return ground_truth, cast, index, claims, graph


def human(minutes: float) -> str:
    if minutes < 90:
        return f"{minutes:.0f} min"
    if minutes < 1440:
        return f"{minutes / 60:.1f} hr"
    return f"{minutes / 1440:.1f} days"


def time_scale_bar(touch: float, internal: float, external: float) -> list[str]:
    """The picture the whole method exists to produce, in the terminal.

    Work and waiting drawn to the same scale. On a real process the work is a sliver, and
    seeing that is the finding - a flowchart of equal-sized boxes hides exactly this.
    """
    span = touch + internal + external
    if span <= 0:
        return ["  (no durations recovered)"]
    widths = [max(1, round(BAR_WIDTH * part / span)) if part > 0 else 0
              for part in (touch, internal, external)]
    bar = "█" * widths[0] + "▒" * widths[1] + "░" * widths[2]
    return [
        f"  {bar}",
        f"  █ work {touch / span:6.2%}   ▒ waiting on us {internal / span:6.2%}   "
        f"░ waiting on others {external / span:6.2%}",
    ]


def report(process_dir: Path) -> int:
    ground_truth, cast, index, claims, graph = load(process_dir)
    computed = metrics_module.compute(graph)
    names = {member.person_id: member.name for member in cast}
    organisation = ground_truth["organisation"]

    print(f"\n{organisation['name']} — {ground_truth['domain']}")
    print(f"{organisation['headcount']} people · {organisation['sector']}")
    print(f"{sum(len(one) for one in claims.values())} claims from {len(claims)} interviews\n")

    print("TIME")
    print(f"  work {human(computed.touch_minutes)} spread across "
          f"{human(computed.touch_minutes + computed.queue_minutes)} elapsed")
    print(f"  cycle efficiency {computed.cycle_efficiency:.2%}\n")
    for line in time_scale_bar(
        computed.touch_minutes, computed.internal_wait_minutes, computed.external_wait_minutes
    ):
        print(line)

    print("\nWHERE THE DELAY IS  (by time attributed, not by who complains)")
    ranked = computed.ranked_by_delay()
    by_complaints = [person.person_id for person in computed.ranked_by_complaints()]
    for position, person in enumerate(ranked, start=1):
        complaint_rank = by_complaints.index(person.person_id) + 1
        marker = "  <- complained about most" if complaint_rank == 1 else ""
        print(f"  {position}. {names.get(person.person_id, person.person_id):<20}"
              f" {human(person.attributed_queue):>10} attributed"
              f"   (complaint rank {complaint_rank}){marker}")

    schedules = computed.ranked_schedules()
    if schedules:
        print("\nWHAT MAKES WORK WAIT  (cadences, which have no counterparty to blame)")
        for cadence in schedules[:5]:
            owner = "several people" if cadence.declared_by == "multiple" else names.get(
                cadence.declared_by, cadence.declared_by
            )
            waiting = ", ".join(sorted(names.get(one, one) for one in cadence.waiters))
            print(f"  {human(cadence.attributed_queue):>10}  {cadence.label}")
            print(f"              run by {owner} · holds up {waiting}")

    mentions: dict[tuple[str, str], list[dict]] = {}
    for speaker, speaker_claims in claims.items():
        speaker_aliases = aliases_for(speaker, names.get(speaker, speaker))
        for claim in speaker_claims:
            for mention in named_counterparties(claim, speaker_aliases):
                subject = resolve_person(mention, index)
                if subject and subject != speaker:
                    mentions.setdefault((speaker, subject), []).append(claim)

    fractures = find_fractures(mentions)
    print(f"\nFRACTURES  ({len(fractures)} found)")
    if not fractures:
        print("  none")
    for fracture in fractures:
        print(f"  [{fracture.kind}] {names.get(fracture.claimant, fracture.claimant)}"
              f" / {names.get(fracture.counterparty, fracture.counterparty)}")
        print(f"      {fracture.summary}")
        for claim in fracture.claimant_claims[:2]:
            print(f"      \"{claim['verbatim'][:78]}\"")

    print()
    return 0


def show_score(process_dir: Path) -> int:
    ground_truth, _, _, _, graph = load(process_dir)
    computed = metrics_module.compute(graph)
    criteria = score(computed, ground_truth)
    print(f"\n{process_dir.name}")
    for criterion in criteria:
        print(f"  {'PASS' if criterion.passed else 'FAIL'} "
              f"{criterion.name:<40} {criterion.detail}")
    passed = sum(criterion.passed for criterion in criteria)
    print(f"\n  {passed}/{len(criteria)} criteria pass\n")
    return 0 if passed == len(criteria) else 1


def list_processes() -> int:
    print()
    for path in sorted(CORPUS_ROOT.iterdir()):
        if (path / "claims").exists():
            ground_truth = json.loads((path / "ground_truth.json").read_text())
            print(f"  {path.name:<38} {ground_truth['organisation']['name']}"
                  f" · {len(ground_truth['steps'])} steps"
                  f" · {len(ground_truth['cast'])} people")
        elif (path / "ground_truth.json").exists():
            print(f"  {path.name:<38} (no claims extracted yet)")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m analyzer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=False)
    for name, help_text in (
        ("report", "analyse a process and print what was found"),
        ("score", "score the analysis against the hidden ground truth"),
    ):
        one = sub.add_parser(name, help=help_text)
        one.add_argument("process", help="path, name, or unambiguous prefix")
    sub.add_parser("list", help="list available processes")

    arguments = parser.parse_args()
    if arguments.command is None:
        return list_processes()
    if arguments.command == "list":
        return list_processes()
    if arguments.command == "report":
        return report(find_process(arguments.process))
    return show_score(find_process(arguments.process))


if __name__ == "__main__":
    raise SystemExit(main())
