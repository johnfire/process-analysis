"""Derived quantities. All arithmetic, no model, no judgment.

The load-bearing one is the queue gap. Per CAPTURE.md, the most valuable numbers in a
process are differences between accounts rather than values inside any single account: a
person underestimates the time work sits with them and overestimates how long it sits with
everybody else, so the gap between what they claim and what their colleagues attribute to
them is a quantity nobody in the organisation holds.

Findings rank by magnitude of waiting, never by how loudly anyone complained. The corpus
plants a loud cheap step specifically to check that.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from analyzer.graph import Interval, ProcessGraph


def total(intervals: list[Interval]) -> float:
    return sum(interval.midpoint for interval in intervals)


def typical(intervals: list[Interval]) -> float:
    return median(interval.midpoint for interval in intervals) if intervals else 0.0


@dataclass(frozen=True)
class PersonMetrics:
    person_id: str
    touch_minutes: float
    self_reported_queue: float
    attributed_queue: float
    complaints: int

    @property
    def queue_gap(self) -> float:
        """What colleagues attribute to waiting on this person, minus what they admit to.

        Positive means others experience more delay here than the person reports. Neither
        side can compute it; it exists only across two accounts.
        """
        return self.attributed_queue - self.self_reported_queue


@dataclass(frozen=True)
class ScheduleMetrics:
    """A cadence that makes work wait, and the people it makes wait."""

    label: str
    declared_by: str
    waiters: frozenset[str]
    attributed_queue: float


@dataclass(frozen=True)
class ProcessMetrics:
    people: list[PersonMetrics]
    schedules: list[ScheduleMetrics]
    internal_wait_minutes: float
    external_wait_minutes: float
    unresolved_mentions: int

    @property
    def touch_minutes(self) -> float:
        return sum(person.touch_minutes for person in self.people)

    @property
    def queue_minutes(self) -> float:
        return self.internal_wait_minutes + self.external_wait_minutes

    @property
    def cycle_efficiency(self) -> float:
        span = self.touch_minutes + self.queue_minutes
        return self.touch_minutes / span if span else 0.0

    @property
    def external_share(self) -> float:
        """Waiting that no redesign can collapse, as a fraction of all waiting."""
        return self.external_wait_minutes / self.queue_minutes if self.queue_minutes else 0.0

    def ranked_schedules(self) -> list[ScheduleMetrics]:
        """Cadences ordered by the delay they cause.

        A batch has no opinion, so it can never appear in a person ranking - but it can be
        the largest single source of waiting in a process, and in a batch-driven process it
        usually is.
        """
        return sorted(
            self.schedules, key=lambda one: one.attributed_queue, reverse=True
        )

    def ranked_by_delay(self) -> list[PersonMetrics]:
        """Bottleneck ranking: by attributed delay, never by complaint volume."""
        return sorted(
            self.people,
            key=lambda person: (person.attributed_queue, person.queue_gap),
            reverse=True,
        )

    def ranked_by_complaints(self) -> list[PersonMetrics]:
        """Only ever computed to demonstrate the two rankings differ."""
        return sorted(self.people, key=lambda person: person.complaints, reverse=True)


def compute(graph: ProcessGraph) -> ProcessMetrics:
    attributed: dict[str, list[Interval]] = {person_id: [] for person_id in graph.nodes}
    for (_, target), edge in graph.edges.items():
        attributed.setdefault(target, []).extend(edge.attributed_queue)

    people = [
        PersonMetrics(
            person_id=person_id,
            touch_minutes=total(node.touch),
            self_reported_queue=total(node.queue_self_reported),
            attributed_queue=total(attributed.get(person_id, [])),
            complaints=node.complaints,
        )
        for person_id, node in sorted(graph.nodes.items())
    ]
    schedules = [
        ScheduleMetrics(
            label=node.cadence.label,
            declared_by=node.cadence.declared_by,
            waiters=frozenset(node.waiters),
            attributed_queue=total(node.attributed_queue),
        )
        for node in graph.schedules.values()
    ]
    return ProcessMetrics(
        people=people,
        schedules=schedules,
        internal_wait_minutes=sum(total(node.waits_internal) for node in graph.nodes.values()),
        external_wait_minutes=sum(total(node.waits_external) for node in graph.nodes.values()),
        unresolved_mentions=graph.unresolved_mentions,
    )
