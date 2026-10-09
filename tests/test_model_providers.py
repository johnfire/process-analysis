"""Provider calls against a fake HTTP transport: no network, no keys."""

from __future__ import annotations

import json

import httpx
import pytest

from web.model_providers import (
    MAX_ATTEMPTS,
    PROVIDERS,
    ProviderError,
    api_key_for,
    complete,
    parse_completion,
)

SECRET = "sk-test-secret-key"


def client_replying(*responses, seen=None):
    """A client that answers with each response in turn (an Exception is raised instead)."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return httpx.Client(transport=httpx.MockTransport(handler))


def openai_reply(text="[]", finish="stop", prompt_tokens=11, completion_tokens=7):
    body = {
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }
    return httpx.Response(200, json=body)


def anthropic_reply(text="[]", stop="end_turn"):
    body = {
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop,
        "usage": {"input_tokens": 21, "output_tokens": 9},
    }
    return httpx.Response(200, json=body)


NO_PAUSE = lambda seconds: None  # noqa: E731


def test_openai_style_providers_send_a_bearer_key_and_read_the_reply():
    seen: list[httpx.Request] = []
    for name in ("openrouter", "deepseek", "openai"):
        result = complete(
            PROVIDERS[name],
            "some-model",
            "hello",
            SECRET,
            client_replying(openai_reply("hi"), seen=seen),
            NO_PAUSE,
        )
        assert (result.text, result.input_tokens, result.output_tokens) == ("hi", 11, 7)
    assert all(r.headers["authorization"] == f"Bearer {SECRET}" for r in seen)
    assert [str(r.url) for r in seen] == [PROVIDERS[n].url for n in ("openrouter", "deepseek", "openai")]


def test_openai_uses_its_own_output_limit_field():
    seen: list[httpx.Request] = []
    complete(PROVIDERS["openai"], "m", "p", SECRET, client_replying(openai_reply(), seen=seen), NO_PAUSE)
    body = json.loads(seen[0].content)
    assert "max_completion_tokens" in body and "max_tokens" not in body


def test_anthropic_uses_its_own_headers_and_message_shape():
    seen: list[httpx.Request] = []
    result = complete(
        PROVIDERS["anthropic"],
        "claude-x",
        "hello",
        SECRET,
        client_replying(anthropic_reply("ok"), seen=seen),
        NO_PAUSE,
    )
    assert (result.text, result.input_tokens, result.output_tokens) == ("ok", 21, 9)
    request = seen[0]
    assert request.headers["x-api-key"] == SECRET and request.headers["anthropic-version"]
    assert "authorization" not in request.headers
    assert json.loads(request.content)["messages"] == [{"role": "user", "content": "hello"}]


def test_transient_failures_are_retried_then_succeed():
    pauses: list[float] = []
    client = client_replying(
        httpx.Response(429), httpx.Response(503), httpx.ConnectError("down"), openai_reply("finally")
    )
    assert complete(PROVIDERS["deepseek"], "m", "p", SECRET, client, pauses.append).text == "finally"
    assert len(pauses) == 3 and pauses == sorted(pauses)


def test_giving_up_after_the_last_attempt_says_so():
    client = client_replying(*[httpx.Response(503)] * MAX_ATTEMPTS)
    with pytest.raises(ProviderError, match=f"gave up after {MAX_ATTEMPTS} attempts"):
        complete(PROVIDERS["deepseek"], "m", "p", SECRET, client, NO_PAUSE)


def test_a_rejected_request_is_not_retried():
    seen: list[httpx.Request] = []
    client = client_replying(httpx.Response(401, text="invalid api key"), httpx.Response(200), seen=seen)
    with pytest.raises(ProviderError, match="HTTP 401"):
        complete(PROVIDERS["anthropic"], "m", "p", SECRET, client, NO_PAUSE)
    assert len(seen) == 1


def test_the_api_key_never_appears_in_an_error_message():
    client = client_replying(httpx.Response(401, text="bad key"))
    with pytest.raises(ProviderError) as raised:
        complete(PROVIDERS["openai"], "m", "p", SECRET, client, NO_PAUSE)
    assert SECRET not in str(raised.value)


@pytest.mark.parametrize(
    "reply", [openai_reply("[1", finish="length"), anthropic_reply("[1", stop="max_tokens")]
)
def test_a_cut_off_answer_is_an_error_not_a_truncated_result(reply):
    spec = PROVIDERS["anthropic" if "content" in reply.json() else "deepseek"]
    with pytest.raises(ProviderError, match="cut off"):
        complete(spec, "m", "p", SECRET, client_replying(reply), NO_PAUSE)


def test_empty_and_malformed_replies_are_errors():
    with pytest.raises(ProviderError, match="empty"):
        parse_completion(
            PROVIDERS["deepseek"], {"choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]}
        )
    with pytest.raises(ProviderError, match="unexpected shape"):
        parse_completion(PROVIDERS["deepseek"], {"nonsense": True})
    with pytest.raises(ProviderError, match="unexpected shape"):
        parse_completion(PROVIDERS["anthropic"], {"content": "not a list"})


def test_missing_usage_counts_as_zero_tokens_rather_than_failing():
    result = parse_completion(
        PROVIDERS["deepseek"], {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}
    )
    assert (result.input_tokens, result.output_tokens) == (0, 0)


def test_keys_come_from_the_environment_and_blank_means_absent():
    assert api_key_for(PROVIDERS["anthropic"], {"ANTHROPIC_API_KEY": " abc "}) == "abc"
    assert api_key_for(PROVIDERS["anthropic"], {"ANTHROPIC_API_KEY": "  "}) is None
    assert api_key_for(PROVIDERS["anthropic"], {}) is None
