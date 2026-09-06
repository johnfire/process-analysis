"""Score a recovered analysis against the hidden ground truth.

Deterministic throughout, per EVAL.md: these are arithmetic comparisons, not judgments, and
an LLM judge here would add cost, variance and no information.

Scores are reported per criterion rather than as one number. A single blended figure would
let a strong result on cycle efficiency conceal a failure on internal-versus-external
attribution, and those failures mean different things: one says the analysis is imprecise,
the other says it would propose fixing a wait that no redesign can touch.
"""

from __future__ import annotations

from dataclasses import dataclass

from analyzer.metrics import ProcessMetrics


@dataclass(frozen=True)
class Criterion:
    name: str
    passed: bool
    detail: str


def true_person_queue(ground_truth: dict) -> dict[str, float]:
    """Queue minutes attributable to each person, from the answer key."""
    totals: dict[str, float] = {member["person_id"]: 0.0 for member in ground_truth["cast"]}
    for step in ground_truth["steps"]:
        totals[step["performed_by"]] = totals.get(step["performed_by"], 0.0) + step[
            "queue_before_minutes"
        ]
    return totals


def spearman(left: list[float], right: list[float]) -> float:
    """Rank correlation, without pulling in a numerical stack for one statistic."""

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda index: values[index])
        result = [0.0] * len(values)
        position = 0
        while position < len(order):
            end = position
            while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
                end += 1
            shared = (position + end) / 2 + 1
            for index in range(position, end + 1):
                result[order[index]] = shared
            position = end + 1
        return result

    if len(left) < 2:
        return 0.0
    left_ranks, right_ranks = ranks(left), ranks(right)
    mean_left = sum(left_ranks) / len(left_ranks)
    mean_right = sum(right_ranks) / len(right_ranks)
    covariance = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left_ranks, right_ranks)
    )
    spread_left = sum((a - mean_left) ** 2 for a in left_ranks) ** 0.5
    spread_right = sum((b - mean_right) ** 2 for b in right_ranks) ** 0.5
    return covariance / (spread_left * spread_right) if spread_left and spread_right else 0.0


def score(metrics: ProcessMetrics, ground_truth: dict) -> list[Criterion]:
    planted = ground_truth["planted"]
    steps = {step["step_id"]: step for step in ground_truth["steps"]}
    truth = true_person_queue(ground_truth)
    ranked = metrics.ranked_by_delay()
    by_delay = [person.person_id for person in ranked]

    criteria: list[Criterion] = []

    # 1. The bottleneck. The planted silent expensive wait is the one nobody complains about,
    #    so finding it is the whole point rather than a nice extra.
    silent_step = steps.get(planted["silent_expensive_wait"])
    silent_owner = silent_step["performed_by"] if silent_step else None
    position = by_delay.index(silent_owner) + 1 if silent_owner in by_delay else None
    criteria.append(
        Criterion(
            "bottleneck_in_top_three",
            position is not None and position <= 3,
            f"silent expensive wait is {silent_owner}'s; ranked {position} of {len(by_delay)}",
        )
    )

    # 2. Decoy resistance. The loud cheap step must not be mistaken for a bottleneck.
    loud_step = steps.get(planted["loud_cheap_step"])
    loud_owner = loud_step["performed_by"] if loud_step else None
    loud_position = by_delay.index(loud_owner) + 1 if loud_owner in by_delay else None
    by_complaints = [person.person_id for person in metrics.ranked_by_complaints()]
    complaint_position = (
        by_complaints.index(loud_owner) + 1 if loud_owner in by_complaints else None
    )
    criteria.append(
        Criterion(
            "decoy_not_ranked_first",
            loud_position != 1,
            f"loud cheap step is {loud_owner}'s; delay rank {loud_position}, "
            f"complaint rank {complaint_position}",
        )
    )

    # 3. External waiting must not be attributed to an internal cause, or the analysis
    #    proposes fixing something no redesign can reach.
    true_queue = sum(step["queue_before_minutes"] for step in ground_truth["steps"])
    true_external = sum(
        step["queue_before_minutes"]
        for step in ground_truth["steps"]
        if step["queue_owner"] == "external"
    )
    true_share = true_external / true_queue if true_queue else 0.0
    error = abs(metrics.external_share - true_share)
    criteria.append(
        Criterion(
            "external_share_within_20_points",
            error <= 0.20,
            f"recovered {metrics.external_share:.0%} vs true {true_share:.0%}",
        )
    )

    # 4. Severe lopsidedness must survive. Getting the magnitude wrong is tolerable; missing
    #    that the process is almost entirely waiting is not.
    criteria.append(
        Criterion(
            "cycle_efficiency_under_5_percent",
            metrics.cycle_efficiency < 0.05,
            f"recovered {metrics.cycle_efficiency:.2%}",
        )
    )

    # 5. Do the recovered per-person delays order the same way as the real ones?
    shared = [person for person in by_delay if person in truth]
    correlation = spearman(
        [next(p.attributed_queue for p in ranked if p.person_id == person) for person in shared],
        [truth[person] for person in shared],
    )
    criteria.append(
        Criterion(
            "delay_ranking_correlates",
            correlation > 0.3,
            f"spearman {correlation:+.2f} over {len(shared)} people",
        )
    )

    # 6. The two rankings must differ, or ranking by delay is doing no work.
    criteria.append(
        Criterion(
            "delay_ranking_differs_from_complaints",
            by_delay != by_complaints,
            "delay and complaint orderings are distinct",
        )
    )
    return criteria
