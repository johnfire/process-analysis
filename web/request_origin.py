"""Cross-site request forgery defence: refuse state-changing requests that did not start here.

Browsers attach an Origin header to cross-origin POSTs and to same-origin ones; a forged form on
another site therefore arrives with a foreign Origin. Combined with SameSite=Lax session cookies,
this closes the forgery path without per-form tokens.
"""

from __future__ import annotations

from urllib.parse import urlsplit

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def host_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def is_same_origin(origin: str | None, referer: str | None, own_hosts: set[str]) -> bool:
    """True when the request names one of our own hosts as its origin (Referer as the fallback)."""
    claimed = origin if origin and origin != "null" else referer
    if not claimed:
        return False
    return host_of(claimed) in own_hosts


def needs_origin_check(method: str) -> bool:
    return method.upper() in UNSAFE_METHODS
