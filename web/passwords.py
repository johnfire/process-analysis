"""Password hashing (Argon2id) and the password policy. Pure: no database, no request."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 256  # bounds the work an attacker can force per request

_hasher = PasswordHasher()  # argon2-cffi defaults to Argon2id
_DECOY_HASH = _hasher.hash("decoy-password-never-matches")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, candidate: str) -> bool:
    try:
        return _hasher.verify(stored_hash, candidate)
    except (VerificationError, InvalidHashError):
        return False


def spend_verification_time(candidate: str) -> None:
    """Burn the same time a real check takes, so an unknown email is not faster than a wrong password."""
    verify_password(_DECOY_HASH, candidate)


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def password_problem(password: str, email: str) -> str | None:
    """Why this password is not acceptable, or None when it is."""
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        return f"Use at least {MINIMUM_PASSWORD_LENGTH} characters."
    if len(password) > MAXIMUM_PASSWORD_LENGTH:
        return f"Use at most {MAXIMUM_PASSWORD_LENGTH} characters."
    if password.lower() == email.strip().lower():
        return "The password must not be your email address."
    if len(set(password)) < 5:
        return "That password is too repetitive."
    return None
