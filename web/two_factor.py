"""TOTP (RFC 6238) second factor. Pure functions over a secret, a code and the clock."""

from __future__ import annotations

import hmac
import time

import pyotp
import segno

STEP_SECONDS = 30
ISSUER = "Process Analysis"
ACCEPTED_STEP_DRIFT = 1  # one step either side tolerates a slightly wrong phone clock


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_code_svg(uri: str) -> str:
    return segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#000000", light="#ffffff")


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def accepted_step(
    secret: str, typed_code: str, last_used_step: int | None, now: float | None = None
) -> int | None:
    """The time step this code proves, or None.

    A step at or before the last one accepted is refused, so a code that was seen (shoulder-surfed,
    phished) cannot be replayed inside its own 30-second window.
    """
    code = typed_code.strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    totp = pyotp.TOTP(secret)
    centre = current_step(now)
    for step in range(centre - ACCEPTED_STEP_DRIFT, centre + ACCEPTED_STEP_DRIFT + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(totp.at(step * STEP_SECONDS), code):
            return step
    return None
