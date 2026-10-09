"""Talking to model providers over HTTP: OpenRouter, DeepSeek, Anthropic and OpenAI.

One function, `complete`, turns a prompt into text and reports the tokens it cost. Transient
failures (rate limits, server errors, timeouts) are retried with growing pauses; anything else, and
any reply that was cut off mid-way, raises ProviderError so the caller can record why one
transcript failed without losing the others. API keys are passed in and never logged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 300.0
MAX_ATTEMPTS = 4
RETRY_PAUSES_SECONDS = (2.0, 5.0, 12.0)
ANTHROPIC_VERSION = "2023-06-01"
RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})
ERROR_EXCERPT_CHARACTERS = 300


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    label: str
    url: str
    key_variable: str
    api_style: str  # "openai" (chat completions) or "anthropic" (messages)
    suggested_model: str
    max_output_tokens: int
    output_limit_field: str = "max_tokens"


# Suggested models are starting points that the operator edits in the form; model names change
# faster than this file does, so none of them is treated as authoritative.
PROVIDERS: dict[str, ProviderSpec] = {
    spec.name: spec
    for spec in (
        ProviderSpec(
            "openrouter",
            "OpenRouter",
            "https://openrouter.ai/api/v1/chat/completions",
            "OPENROUTER_API_KEY",
            "openai",
            "deepseek/deepseek-chat",
            16000,
        ),
        ProviderSpec(
            "deepseek",
            "DeepSeek",
            "https://api.deepseek.com/chat/completions",
            "DEEPSEEK_API_KEY",
            "openai",
            "deepseek-chat",
            8192,
        ),
        ProviderSpec(
            "anthropic",
            "Anthropic",
            "https://api.anthropic.com/v1/messages",
            "ANTHROPIC_API_KEY",
            "anthropic",
            "claude-sonnet-5-5",
            16000,
        ),
        ProviderSpec(
            "openai",
            "OpenAI",
            "https://api.openai.com/v1/chat/completions",
            "OPENAI_API_KEY",
            "openai",
            "",
            16000,
            "max_completion_tokens",
        ),
    )
}


class ProviderError(Exception):
    """A call that failed for a reason the caller should record, not retry."""


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


def request_parts(
    spec: ProviderSpec, model: str, prompt: str, api_key: str
) -> tuple[dict[str, str], dict[str, Any]]:
    messages = [{"role": "user", "content": prompt}]
    if spec.api_style == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        return headers, {"model": model, "max_tokens": spec.max_output_tokens, "messages": messages}
    headers = {"authorization": f"Bearer {api_key}", "content-type": "application/json"}
    return headers, {"model": model, spec.output_limit_field: spec.max_output_tokens, "messages": messages}


def parse_completion(spec: ProviderSpec, payload: Mapping[str, Any]) -> Completion:
    """Read a provider's reply; raise ProviderError when it is empty or was cut off."""
    try:
        if spec.api_style == "anthropic":
            text = "".join(
                block.get("text", "") for block in payload["content"] if block.get("type") == "text"
            )
            was_cut_off = payload.get("stop_reason") == "max_tokens"
            usage = payload.get("usage", {})
            tokens = (int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))
        else:
            choice = payload["choices"][0]
            text = choice["message"]["content"] or ""
            was_cut_off = choice.get("finish_reason") == "length"
            usage = payload.get("usage", {})
            tokens = (int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as error:
        raise ProviderError(f"{spec.label} sent a reply in an unexpected shape ({error!r})") from error
    if was_cut_off:
        raise ProviderError(
            f"{spec.label}'s answer was cut off at its output limit; "
            "the transcript is too long for this model"
        )
    if not text.strip():
        raise ProviderError(f"{spec.label} returned an empty answer")
    return Completion(text, *tokens)


def error_excerpt(response: httpx.Response) -> str:
    return response.text[:ERROR_EXCERPT_CHARACTERS].replace("\n", " ")


def complete(
    spec: ProviderSpec,
    model: str,
    prompt: str,
    api_key: str,
    client: httpx.Client | None = None,
    pause: Callable[[float], None] = time.sleep,
) -> Completion:
    """Send one prompt and return the text. Retries transient failures; raises ProviderError otherwise."""
    headers, body = request_parts(spec, model, prompt, api_key)
    owns_client = client is None
    http = client or httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS)
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = http.post(spec.url, headers=headers, json=body)
            except httpx.TransportError as error:
                reason = f"could not reach {spec.label} ({type(error).__name__})"
            else:
                if response.status_code == 200:
                    return parse_completion(spec, response.json())
                if response.status_code not in RETRYABLE_STATUSES:
                    raise ProviderError(
                        f"{spec.label} refused the request: "
                        f"HTTP {response.status_code} {error_excerpt(response)}"
                    )
                reason = f"{spec.label} answered HTTP {response.status_code}"
            if attempt == MAX_ATTEMPTS:
                raise ProviderError(f"{reason}; gave up after {MAX_ATTEMPTS} attempts")
            log.warning("%s; retrying (attempt %d)", reason, attempt)
            pause(RETRY_PAUSES_SECONDS[min(attempt - 1, len(RETRY_PAUSES_SECONDS) - 1)])
    finally:
        if owns_client:
            http.close()
    raise ProviderError("unreachable")  # the loop always returns or raises


def api_key_for(spec: ProviderSpec, environment: Mapping[str, str]) -> str | None:
    key = environment.get(spec.key_variable, "").strip()
    return key or None
