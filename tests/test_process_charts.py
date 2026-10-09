from __future__ import annotations

import re

from web.process_charts import (
    MINIMUM_SLIVER_WIDTH,
    TIMELINE_WIDTH,
    contrast_svg,
    segment_widths,
    timeline_svg,
)


def time_of(touch, internal, external):
    return {"touch_minutes": touch, "internal_wait_minutes": internal, "external_wait_minutes": external}


def person(name, delay_rank, complaint_rank, attributed=0.0, complaints=1, has_evidence=True):
    return {
        "name": name,
        "delay_rank": delay_rank,
        "complaint_rank": complaint_rank,
        "attributed_queue": attributed,
        "complaints": complaints,
        "has_time_evidence": has_evidence,
    }


def test_segments_fill_the_track_exactly():
    assert sum(segment_widths(350, 24000, 52000)) == TIMELINE_WIDTH
    assert sum(segment_widths(0, 100, 100)) == TIMELINE_WIDTH


def test_a_vanishing_slice_of_work_is_still_drawn():
    work, _, _ = segment_widths(1, 1_000_000, 1_000_000)
    assert work == MINIMUM_SLIVER_WIDTH


def test_work_wider_than_the_minimum_is_drawn_to_scale():
    work, _, _ = segment_widths(500, 250, 250)
    assert work == TIMELINE_WIDTH / 2


def test_no_work_means_no_work_rectangle():
    svg = timeline_svg(time_of(0, 100, 100))
    assert "tl-work" not in svg


def test_all_three_parts_are_drawn_with_accessible_labels():
    svg = timeline_svg(time_of(350, 24000, 52000))
    for css_class in ("tl-work", "tl-internal", "tl-external"):
        assert css_class in svg
    assert 'role="img"' in svg and "aria-label=" in svg and "<title>work:" in svg


def test_no_durations_gives_no_chart_rather_than_an_empty_one():
    assert timeline_svg(time_of(0, 0, 0)) is None


def test_contrast_draws_one_line_per_person_and_marks_the_loudest():
    people = [person("A", 1, 2, 500), person("B", 2, 1, 100)]
    svg = contrast_svg(people)
    assert len(re.findall(r"<line ", svg)) == 2
    assert svg.count("ct-line-loudest") == 1


def test_a_person_with_no_evidence_gets_words_not_a_short_bar():
    svg = contrast_svg([person("A", 1, 1, 500), person("Nobody", 2, 2, 0, has_evidence=False)])
    assert svg.count("ct-bar-delay") == 1
    assert "no time evidence" in svg


def test_names_are_escaped_in_the_svg():
    svg = contrast_svg([person("<script>alert(1)</script>", 1, 1, 10)])
    assert "<script>" not in svg and "&lt;script&gt;" in svg


def test_no_people_means_no_chart():
    assert contrast_svg([]) is None
