"""A plausibility check for email addresses typed by a person. It catches placeholders and typos,
not undeliverable mailboxes: the only real test of an address is sending mail to it."""

from __future__ import annotations

MAX_ADDRESS_CHARACTERS = 320


def is_plausible_email(address: str) -> bool:
    local, separator, domain = address.partition("@")
    labels = domain.split(".")
    return (
        separator == "@"
        and bool(local)
        and "@" not in domain
        and " " not in address
        and len(address) <= MAX_ADDRESS_CHARACTERS
        and len(labels) >= 2
        and all(labels)
    )
