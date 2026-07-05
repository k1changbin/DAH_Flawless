"""Role-scoped LLM adapter with deterministic fallback.

The project can use an external OpenAI-compatible LLM as a reviewer, but the
simulation must keep running when that endpoint is disabled, disconnected, or
returns invalid JSON. This module centralizes that contract so each role can
provide a small local fallback instead of duplicating HTTP and parsing logic.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


FallbackFn = Callable[[str | None], dict]
ValidatorFn = Callable[[dict], None]


@dataclass(frozen=True)
class LLMAdapterConfig:
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = "http://127.0.0.1:8000/v1"
    model: str = "local-reviewer"
    api_key: str = "EMPTY"
    timeout_s: float = 2.0
    fallback_on_error: bool = True

    @classmethod
    def from_mapping(
        cls,
        mapping: dict | None,
        *,
        enabled_env: str | None = None,
        provider_env: str | None = None,
        base_url_env: str = "DAH_LLM_BASE_URL",
        model_env: str = "DAH_LLM_MODEL",
        api_key_env: str = "DAH_LLM_API_KEY",
        timeout_env: str = "DAH_LLM_TIMEOUT_S",
    ) -> "LLMAdapterConfig":
        data = dict(mapping or {})
        if enabled_env and os.getenv(enabled_env):
            data["enabled"] = os.getenv(enabled_env, "").lower() in {"1", "true", "yes", "on"}
        if provider_env and os.getenv(provider_env):
            data["provider"] = os.getenv(provider_env)
        if os.getenv(base_url_env):
            data["base_url"] = os.getenv(base_url_env)
        if os.getenv(model_env):
            data["model"] = os.getenv(model_env)
        if os.getenv(api_key_env):
            data["api_key"] = os.getenv(api_key_env)
        if os.getenv(timeout_env):
            data["timeout_s"] = os.getenv(timeout_env)

        return cls(
            enabled=bool(data.get("enabled", False)),
            provider=str(data.get("provider", "openai_compatible")),
            base_url=str(data.get("base_url", "http://127.0.0.1:8000/v1")),
            model=str(data.get("model", "local-reviewer")),
            api_key=str(data.get("api_key", "EMPTY")),
            timeout_s=float(data.get("timeout_s", 2.0)),
            fallback_on_error=bool(data.get("fallback_on_error", True)),
        )


@dataclass(frozen=True)
class LLMJsonResult:
    data: dict
    external_used: bool
    provider: str
    role_name: str
    fallback_reason: str | None = None
    raw_response: dict | None = None


class LLMJsonAdapter:
    """Call an external JSON LLM or execute a local fallback."""

    def __init__(self, config: LLMAdapterConfig, *, role_name: str):
        self.config = config
        self.role_name = role_name

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        fallback: FallbackFn,
        validator: ValidatorFn | None = None,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> LLMJsonResult:
        if not self.config.enabled:
            return self._fallback(fallback, "external_llm_disabled")

        if self.config.provider != "openai_compatible":
            return self._fallback_or_raise(fallback, f"unsupported_provider:{self.config.provider}")

        try:
            raw = self._call_openai_compatible(
                system_prompt=system_prompt,
                user_payload=user_payload,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = raw["choices"][0]["message"]["content"]
            data = parse_json_object(content)
            if validator is not None:
                validator(data)
            return LLMJsonResult(
                data=data,
                external_used=True,
                provider=self.config.provider,
                role_name=self.role_name,
                raw_response=raw,
            )
        except Exception as exc:
            return self._fallback_or_raise(fallback, str(exc))

    def _fallback_or_raise(self, fallback: FallbackFn, reason: str) -> LLMJsonResult:
        if not self.config.fallback_on_error:
            raise RuntimeError(reason)
        return self._fallback(fallback, reason)

    def _fallback(self, fallback: FallbackFn, reason: str | None) -> LLMJsonResult:
        return LLMJsonResult(
            data=fallback(reason),
            external_used=False,
            provider="fallback",
            role_name=self.role_name,
            fallback_reason=reason,
        )

    def _call_openai_compatible(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, sort_keys=True)},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc)) from exc


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(text[start : end + 1])
