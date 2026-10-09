"""A finished analysis as plain JSON: the one thing the viewer reads.

The hosted viewer never runs the analyzer when a page loads. It reads a stored document built by
this function, so a page is a lookup, an old result stays viewable after the analyzer changes,
and two analyzer versions can be compared side by side.
"""

from __future__ import annotations

from typing import Any

from analyzer.analysis import ANALYZER_VERSION, ProcessAnalysis
from analyzer.fracture import Fracture
from analyzer.score import score

QUOTES_PER_SIDE = 4


def quote_reference(claim: dict) -> dict[str, Any]:
    return {
        "id": claim.get("id"),
        "respondent_id": claim.get("respondent_id"),
        "kind": claim.get("kind"),
        "verbatim": claim.get("verbatim", ""),
    }


def fracture_entry(fracture: Fracture, names: dict[str, str]) -> dict[str, Any]:
    claimant = names.get(fracture.claimant, fracture.claimant)
    counterparty = names.get(fracture.counterparty, fracture.counterparty)
    if fracture.kind == "silence":
        summary = (
            f"{claimant} describes an active dependency on {counterparty}; "
            f"{counterparty}'s account never mentions {claimant}."
        )
    else:
        summary = f"{claimant} and {counterparty} both describe their shared work, incompatibly."
    return {
        "kind": fracture.kind,
        "summary": summary,
        "claimant": {"id": fracture.claimant, "name": claimant},
        "counterparty": {"id": fracture.counterparty, "name": counterparty},
        "claimant_claims": [quote_reference(c) for c in fracture.claimant_claims[:QUOTES_PER_SIDE]],
        "counterparty_claims": [quote_reference(c) for c in fracture.counterparty_claims[:QUOTES_PER_SIDE]],
    }


def people_entries(analysis: ProcessAnalysis) -> list[dict[str, Any]]:
    """People in delay order, each carrying both ranks so the viewer can draw the contrast."""
    roles = {member.person_id: member.role for member in analysis.cast}
    names = {member.person_id: member.name for member in analysis.cast}
    by_delay = analysis.metrics.ranked_by_delay()
    complaint_order = [p.person_id for p in analysis.metrics.ranked_by_complaints()]
    return [
        {
            "person_id": person.person_id,
            "name": names.get(person.person_id, person.person_id),
            "role": roles.get(person.person_id, ""),
            "touch_minutes": person.touch_minutes,
            "self_reported_queue": person.self_reported_queue,
            "attributed_queue": person.attributed_queue,
            "queue_gap": person.queue_gap,
            "complaints": person.complaints,
            "has_time_evidence": person.attributed_count > 0,
            "delay_rank": position,
            "complaint_rank": complaint_order.index(person.person_id) + 1,
        }
        for position, person in enumerate(by_delay, start=1)
    ]


def schedule_entries(analysis: ProcessAnalysis) -> list[dict[str, Any]]:
    names = {member.person_id: member.name for member in analysis.cast}
    entries = []
    for cadence in analysis.metrics.ranked_schedules():
        several = cadence.declared_by == "multiple"
        entries.append(
            {
                "label": cadence.label,
                "run_by": "several people"
                if several
                else names.get(cadence.declared_by, cadence.declared_by),
                "waiters": sorted(names.get(one, one) for one in cadence.waiters),
                "attributed_queue": cadence.attributed_queue,
                "has_time_evidence": cadence.attributed_count > 0,
            }
        )
    return entries


def build_result_document(
    analysis: ProcessAnalysis,
    claim_set: str,
    organisation: dict[str, Any],
    domain: str,
    ground_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = analysis.metrics
    names = {member.person_id: member.name for member in analysis.cast}
    criteria = score(metrics, ground_truth) if ground_truth else None
    return {
        "analyzer_version": ANALYZER_VERSION,
        "claim_set": claim_set,
        "organisation": {key: organisation.get(key) for key in ("name", "sector", "headcount")},
        "domain": domain,
        "interviews": analysis.interview_count,
        "claims": analysis.claim_count,
        "time": {
            "touch_minutes": metrics.touch_minutes,
            "internal_wait_minutes": metrics.internal_wait_minutes,
            "external_wait_minutes": metrics.external_wait_minutes,
            "queue_minutes": metrics.queue_minutes,
            "cycle_efficiency": metrics.cycle_efficiency,
            "external_share": metrics.external_share,
        },
        "people": people_entries(analysis),
        "schedules": schedule_entries(analysis),
        "fractures": [fracture_entry(f, names) for f in analysis.fractures],
        "unresolved_mentions": metrics.unresolved_mentions,
        "score": (
            [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in criteria]
            if criteria is not None
            else None
        ),
    }


def document_from_ground_truth(
    ground_truth: dict[str, Any], claim_set: str, claims_by_person: dict[str, list[dict]]
) -> dict[str, Any]:
    """Analyse one claim set of a synthetic process and score it against its answer key."""
    from analyzer.analysis import analyse
    from analyzer.resolve import Person

    cast = [Person(m["person_id"], m["name"], m["role"]) for m in ground_truth["cast"]]
    analysis = analyse(cast, claims_by_person)
    return build_result_document(
        analysis, claim_set, ground_truth["organisation"], ground_truth["domain"], ground_truth
    )
