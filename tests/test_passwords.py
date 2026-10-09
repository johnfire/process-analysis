from __future__ import annotations

from web.passwords import (
    MAXIMUM_PASSWORD_LENGTH,
    MINIMUM_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    password_problem,
    verify_password,
)


def test_hash_is_argon2id_and_never_the_password():
    stored = hash_password("correct horse battery staple")
    assert stored.startswith("$argon2id$")
    assert "correct horse" not in stored


def test_same_password_hashes_differently_each_time():
    assert hash_password("same password here") != hash_password("same password here")


def test_right_password_verifies_wrong_one_does_not():
    stored = hash_password("correct horse battery staple")
    assert verify_password(stored, "correct horse battery staple")
    assert not verify_password(stored, "correct horse battery stapl")


def test_garbage_stored_hash_fails_closed():
    assert not verify_password("not-a-hash", "anything at all")
    assert not verify_password("", "anything at all")


def test_fresh_hash_does_not_need_rehash():
    assert not needs_rehash(hash_password("correct horse battery staple"))


def test_short_password_is_rejected():
    assert str(MINIMUM_PASSWORD_LENGTH) in (
        password_problem("a" * (MINIMUM_PASSWORD_LENGTH - 1), "x@y.de") or ""
    )


def test_overlong_password_is_rejected():
    assert password_problem("a1" * MAXIMUM_PASSWORD_LENGTH, "x@y.de") is not None


def test_password_equal_to_email_is_rejected_regardless_of_case():
    assert password_problem("Chris.Rehm@Example.com", "chris.rehm@example.com") is not None


def test_repetitive_password_is_rejected():
    assert password_problem("aaaaaaaaaaaaaaaa", "x@y.de") is not None


def test_a_passphrase_is_accepted():
    assert password_problem("walnut river lantern mosaic", "x@y.de") is None
