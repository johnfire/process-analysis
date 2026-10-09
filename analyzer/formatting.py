"""Human-readable renderings of analyzer quantities, shared by the terminal and the web app."""

from __future__ import annotations


def human(minutes: float) -> str:
    """A duration in the unit a person would say it in: minutes, hours or days."""
    if minutes < 90:
        return f"{minutes:.0f} min"
    if minutes < 1440:
        return f"{minutes / 60:.1f} hr"
    return f"{minutes / 1440:.1f} days"
