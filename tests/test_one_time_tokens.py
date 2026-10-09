from __future__ import annotations

import re

from web.one_time_tokens import (
    RECOVERY_CODE_COUNT,
    hash_token,
    looks_like_recovery_code,
    new_recovery_code,
    new_recovery_codes,
    new_token,
    normalise_recovery_code,
    tokens_match,
)


def test_new_token_returns_raw_and_its_hash():
    raw, hashed = new_token()
    assert hash_token(raw) == hashed
    assert raw != hashed
    assert len(hashed) == 64


def test_tokens_are_unique_and_long_enough_to_guess_never():
    raws = {new_token()[0] for _ in range(200)}
    assert len(raws) == 200
    assert all(len(raw) >= 40 for raw in raws)


def test_recovery_code_shape():
    assert re.fullmatch(r"[a-z2-9]{5}-[a-z2-9]{5}", new_recovery_code())


def test_recovery_codes_exclude_lookalike_characters():
    joined = "".join(new_recovery_codes() * 20)
    assert not set("il01o") & set(joined)


def test_recovery_code_batch_is_distinct():
    codes = new_recovery_codes()
    assert len(codes) == RECOVERY_CODE_COUNT == len(set(codes))


def test_typed_recovery_code_is_normalised():
    assert normalise_recovery_code("  ABCDE-FGHJK ") == "abcde-fghjk"
    assert normalise_recovery_code("abcde -fghjk") == "abcde-fghjk"


def test_recovery_code_is_told_apart_from_a_totp_code():
    assert looks_like_recovery_code("abcde-fghjk")
    assert not looks_like_recovery_code("123456")
    assert not looks_like_recovery_code("123 456")


def test_token_comparison():
    assert tokens_match(hash_token("a"), hash_token("a"))
    assert not tokens_match(hash_token("a"), hash_token("b"))
