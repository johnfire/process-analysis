"""Which providers a client's data may go to. Pure, and checked twice: by the form and by the worker."""

from __future__ import annotations

SENSITIVE = "sensitive"
STANDARD = "standard"
SENSITIVITY_LEVELS = (SENSITIVE, STANDARD)


def parse_provider_list(raw: str) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def allowed_providers(
    sensitivity: str, enabled: tuple[str, ...], approved_for_sensitive: tuple[str, ...]
) -> list[str]:
    """Providers usable for this client's data.

    Sensitive data may only go to providers the operator has personally approved after reading
    their data-handling terms (SENSITIVE_OK_PROVIDERS). With nothing approved, nothing is allowed,
    which is the safe default. Anything that is not exactly "standard" is treated as sensitive.
    """
    if sensitivity == STANDARD:
        return [name for name in enabled]
    return [name for name in enabled if name in approved_for_sensitive]


def is_allowed(provider: str, sensitivity: str, enabled: tuple[str, ...], approved: tuple[str, ...]) -> bool:
    return provider in allowed_providers(sensitivity, enabled, approved)
