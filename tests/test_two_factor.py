from __future__ import annotations

import pyotp

from web.two_factor import (
    STEP_SECONDS,
    accepted_step,
    current_step,
    new_secret,
    provisioning_uri,
    qr_code_svg,
)

NOW = 1_800_000_000.0  # any fixed instant


def code_at(secret: str, step: int) -> str:
    return pyotp.TOTP(secret).at(step * STEP_SECONDS)


def test_current_code_is_accepted_and_returns_its_step():
    secret = new_secret()
    step = current_step(NOW)
    assert accepted_step(secret, code_at(secret, step), None, NOW) == step


def test_one_step_of_clock_drift_is_tolerated_both_ways():
    secret = new_secret()
    step = current_step(NOW)
    assert accepted_step(secret, code_at(secret, step - 1), None, NOW) == step - 1
    assert accepted_step(secret, code_at(secret, step + 1), None, NOW) == step + 1


def test_two_steps_of_drift_is_refused():
    secret = new_secret()
    assert accepted_step(secret, code_at(secret, current_step(NOW) - 2), None, NOW) is None


def test_a_code_cannot_be_replayed():
    secret = new_secret()
    step = current_step(NOW)
    code = code_at(secret, step)
    assert accepted_step(secret, code, last_used_step=step, now=NOW) is None


def test_an_older_code_cannot_be_used_after_a_newer_one():
    secret = new_secret()
    step = current_step(NOW)
    assert accepted_step(secret, code_at(secret, step - 1), last_used_step=step, now=NOW) is None


def test_a_wrong_code_is_refused():
    secret = "JBSWY3DPEHPK3PXP"  # fixed, so the "wrong" code below is wrong every run
    step = current_step(NOW)
    valid = {code_at(secret, candidate) for candidate in range(step - 1, step + 2)}
    wrong = next(f"{n:06d}" for n in range(1_000_000) if f"{n:06d}" not in valid)
    assert accepted_step(secret, wrong, None, NOW) is None


def test_malformed_codes_are_refused():
    secret = new_secret()
    for malformed in ("", "abc", "12345", "1234567", "12 34 5x"):
        assert accepted_step(secret, malformed, None, NOW) is None


def test_spaces_in_a_typed_code_are_ignored():
    secret = new_secret()
    step = current_step(NOW)
    code = code_at(secret, step)
    assert accepted_step(secret, f"{code[:3]} {code[3:]}", None, NOW) == step


def test_provisioning_uri_names_issuer_and_account():
    uri = provisioning_uri("JBSWY3DPEHPK3PXP", "a@b.de")
    assert uri.startswith("otpauth://totp/")
    assert "Process%20Analysis" in uri
    assert "a%40b.de" in uri


def test_qr_code_is_an_svg():
    assert qr_code_svg("otpauth://totp/x?secret=ABC").lstrip().startswith("<svg")
