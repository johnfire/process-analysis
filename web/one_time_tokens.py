"""Single-use secrets: invite and reset links, session cookies, recovery codes.

Only the SHA-256 of a token is stored. The raw value exists in the email, the cookie or the screen
and nowhere else, so a copy of the database yields no usable link, session or code. These values
are 128+ bits of randomness, so a fast hash is enough; slow hashing is for human-chosen passwords.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

RECOVERY_CODE_COUNT = 8
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alikes (i l o 0 1)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def new_token() -> tuple[str, str]:
    """A fresh token and its hash: (raw, hashed)."""
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_token(raw_token)


def new_recovery_code() -> str:
    characters = [secrets.choice(_RECOVERY_ALPHABET) for _ in range(10)]
    return "".join(characters[:5]) + "-" + "".join(characters[5:])


def new_recovery_codes() -> list[str]:
    return [new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]


def normalise_recovery_code(typed: str) -> str:
    return typed.strip().lower().replace(" ", "")


def looks_like_recovery_code(typed: str) -> bool:
    normalised = normalise_recovery_code(typed)
    return len(normalised) == 11 and normalised[5] == "-"


def tokens_match(first_hash: str, second_hash: str) -> bool:
    return hmac.compare_digest(first_hash, second_hash)
