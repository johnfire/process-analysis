"""The two pictures the method exists to produce, drawn as SVG on the server.

Colours come from CSS classes (site.css), so the charts follow the page palette and need no inline
styles, which the content security policy forbids.
"""

from __future__ import annotations

from typing import Any

from markupsafe import Markup, escape

from analyzer.formatting import human

# ---- Timeline: work and waiting on one honest scale --------------------------------------------

TIMELINE_WIDTH = 1000
TRACK_Y, TRACK_HEIGHT = 16, 56
TIMELINE_HEIGHT = TRACK_Y + TRACK_HEIGHT + 34
MINIMUM_SLIVER_WIDTH = 2.0  # work is often far under a pixel; it is drawn at two so it can be seen


def segment_widths(touch: float, internal: float, external: float) -> tuple[float, float, float]:
    """Drawn widths, summing to the full track. Work is a sliver at minimum; waiting shares the rest."""
    span = touch + internal + external
    work = max(MINIMUM_SLIVER_WIDTH, TIMELINE_WIDTH * touch / span) if touch > 0 else 0.0
    waiting = internal + external
    remaining = TIMELINE_WIDTH - work
    if waiting <= 0:
        return work, 0.0, 0.0
    return work, remaining * internal / waiting, remaining * external / waiting


def timeline_rect(css_class: str, label: str, minutes: float, x: float, width: float) -> str:
    return (
        f'<rect class="{css_class}" x="{x:.2f}" y="{TRACK_Y}" width="{width:.2f}" height="{TRACK_HEIGHT}">'
        f"<title>{escape(label)}: {escape(human(minutes))}</title></rect>"
    )


def timeline_svg(time: dict[str, Any]) -> Markup | None:
    """Work, internal waiting and external waiting on one scale; None when no duration was recovered."""
    touch, internal, external = (
        time["touch_minutes"],
        time["internal_wait_minutes"],
        time["external_wait_minutes"],
    )
    span = touch + internal + external
    if span <= 0:
        return None
    parts = [
        ("tl-work", "work", touch),
        ("tl-internal", "waiting on us", internal),
        ("tl-external", "waiting on others", external),
    ]
    widths = segment_widths(touch, internal, external)
    rects, x = [], 0.0
    for (css_class, label, minutes), width in zip(parts, widths, strict=True):
        if width > 0:
            rects.append(timeline_rect(css_class, label, minutes, x, width))
        x += width
    summary = f"Work {human(touch)} against {human(span)} elapsed, drawn to the same scale."
    axis_y = TRACK_Y + TRACK_HEIGHT + 24
    return Markup(
        f'<svg class="timeline" viewBox="0 0 {TIMELINE_WIDTH} {TIMELINE_HEIGHT}" role="img" '
        f'aria-label="{escape(summary)}" preserveAspectRatio="none">'
        '<defs><pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<line class="tl-hatch-line" x1="0" y1="0" x2="0" y2="8"/></pattern></defs>'
        f'<rect class="tl-track" x="0" y="{TRACK_Y}" width="{TIMELINE_WIDTH}" height="{TRACK_HEIGHT}"/>'
        + "".join(rects)
        + f'<text class="tl-axis" x="0" y="{axis_y}">start</text>'
        f'<text class="tl-axis" x="{TIMELINE_WIDTH}" y="{axis_y}" text-anchor="end">'
        f"{escape(human(span))} elapsed</text></svg>"
    )


# ---- Contrast: who the delay is attributed to, beside who complains ----------------------------

CONTRAST_WIDTH = 1000
ROW_HEIGHT = 44
HEADER_HEIGHT = 34
LEFT_NAME_X, LEFT_BAR_X = 0, 190
LINE_START_X, LINE_END_X = 430, 500
RIGHT_NAME_X, RIGHT_BAR_X = 510, 700
BAR_MAX_WIDTH = 140


def row_centre(rank: int) -> float:
    return HEADER_HEIGHT + (rank - 1) * ROW_HEIGHT + ROW_HEIGHT / 2


def bar(css_class: str, x: float, y: float, width: float, label: str) -> str:
    return (
        f'<rect class="{css_class}" x="{x}" y="{y - 8:.1f}" width="{width:.1f}" height="16"/>'
        f'<text class="ct-value" x="{x + width + 8:.1f}" y="{y + 5:.1f}">{escape(label)}</text>'
    )


def delay_entry(person: dict[str, Any], most: float, y: float) -> str:
    """A person with no time evidence gets words, never a short bar: absence is not a small number."""
    if not person["has_time_evidence"]:
        return f'<text class="ct-noevidence" x="{LEFT_BAR_X}" y="{y + 5:.1f}">no time evidence</text>'
    width = max(2.0, BAR_MAX_WIDTH * person["attributed_queue"] / most) if most else 2.0
    return bar("ct-bar-delay", LEFT_BAR_X, y, width, human(person["attributed_queue"]))


def complaint_entry(person: dict[str, Any], most: int, y: float) -> str:
    width = max(2.0, BAR_MAX_WIDTH * person["complaints"] / most) if most else 2.0
    return bar("ct-bar-complaint", RIGHT_BAR_X, y, width, str(person["complaints"]))


def contrast_line(person: dict[str, Any]) -> str:
    left, right = row_centre(person["delay_rank"]), row_centre(person["complaint_rank"])
    css = "ct-line ct-line-loudest" if person["complaint_rank"] == 1 else "ct-line"
    return f'<line class="{css}" x1="{LINE_START_X}" y1="{left:.1f}" x2="{LINE_END_X}" y2="{right:.1f}"/>'


def contrast_svg(people: list[dict[str, Any]]) -> Markup | None:
    """People ranked by attributed delay on the left and by complaints on the right, joined by a line each."""
    if not people:
        return None
    most_delay = max(p["attributed_queue"] for p in people)
    most_complaints = max(p["complaints"] for p in people)
    height = HEADER_HEIGHT + len(people) * ROW_HEIGHT
    parts = [
        f'<svg class="contrast" viewBox="0 0 {CONTRAST_WIDTH} {height}" role="img" '
        'aria-label="People ranked by attributed delay on the left and by complaints on the right, '
        'joined by one line per person">',
        f'<text class="ct-heading" x="{LEFT_NAME_X}" y="16">By delay attributed to them</text>',
        f'<text class="ct-heading" x="{RIGHT_NAME_X}" y="16">By complaints</text>',
        *(contrast_line(person) for person in people),
    ]
    for person in people:
        y = row_centre(person["delay_rank"])
        parts.append(
            f'<text class="ct-name" x="{LEFT_NAME_X}" y="{y + 5:.1f}">'
            f"{person['delay_rank']}. {escape(person['name'])}</text>"
        )
        parts.append(delay_entry(person, most_delay, y))
    for person in people:
        y = row_centre(person["complaint_rank"])
        parts.append(
            f'<text class="ct-name" x="{RIGHT_NAME_X}" y="{y + 5:.1f}">'
            f"{person['complaint_rank']}. {escape(person['name'])}</text>"
        )
        parts.append(complaint_entry(person, most_complaints, y))
    parts.append("</svg>")
    return Markup("".join(parts))
