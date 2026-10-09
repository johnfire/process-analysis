from __future__ import annotations

from web.provider_policy import SENSITIVE, STANDARD, allowed_providers, is_allowed, parse_provider_list

ENABLED = ("openrouter", "deepseek", "anthropic")


def test_standard_data_may_go_to_any_enabled_provider():
    assert allowed_providers(STANDARD, ENABLED, ()) == list(ENABLED)


def test_sensitive_data_goes_only_to_providers_the_operator_approved():
    assert allowed_providers(SENSITIVE, ENABLED, ("anthropic", "openai")) == ["anthropic"]


def test_with_nothing_approved_sensitive_data_goes_nowhere():
    assert allowed_providers(SENSITIVE, ENABLED, ()) == []


def test_an_unknown_label_is_treated_as_sensitive():
    assert allowed_providers("whatever", ENABLED, ("deepseek",)) == ["deepseek"]


def test_approval_does_not_enable_a_provider_that_is_switched_off():
    assert not is_allowed("openai", SENSITIVE, ENABLED, ("openai",))


def test_parsing_the_environment_list():
    assert parse_provider_list(" OpenRouter, deepseek ,, ") == ("openrouter", "deepseek")
    assert parse_provider_list("") == ()
