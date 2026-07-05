import unittest

from dah_flawless.llm import LLMAdapterConfig, LLMJsonAdapter


class StaticLLMAdapter(LLMJsonAdapter):
    def __init__(self, config: LLMAdapterConfig, content: str):
        super().__init__(config, role_name="unit_test_role")
        self._content = content

    def _call_openai_compatible(self, **kwargs):
        return {"choices": [{"message": {"content": self._content}}]}


class LLMAdapterTests(unittest.TestCase):
    def test_disabled_adapter_uses_fallback(self):
        adapter = LLMJsonAdapter(LLMAdapterConfig(enabled=False), role_name="unit_test_role")

        result = adapter.complete_json(
            system_prompt="Return JSON.",
            user_payload={"x": 1},
            fallback=lambda reason: {"fallback_reason": reason},
        )

        self.assertFalse(result.external_used)
        self.assertEqual(result.data["fallback_reason"], "external_llm_disabled")

    def test_unsupported_provider_uses_fallback(self):
        adapter = LLMJsonAdapter(
            LLMAdapterConfig(enabled=True, provider="unsupported", fallback_on_error=True),
            role_name="unit_test_role",
        )

        result = adapter.complete_json(
            system_prompt="Return JSON.",
            user_payload={"x": 1},
            fallback=lambda reason: {"fallback_reason": reason},
        )

        self.assertFalse(result.external_used)
        self.assertEqual(result.data["fallback_reason"], "unsupported_provider:unsupported")

    def test_valid_external_json_is_returned(self):
        adapter = StaticLLMAdapter(
            LLMAdapterConfig(enabled=True, provider="openai_compatible"),
            '{"decision": "accept", "score": 0.8}',
        )

        result = adapter.complete_json(
            system_prompt="Return JSON.",
            user_payload={"x": 1},
            fallback=lambda reason: {"fallback_reason": reason},
            validator=lambda data: self.assertEqual(data["decision"], "accept"),
        )

        self.assertTrue(result.external_used)
        self.assertEqual(result.data["score"], 0.8)

    def test_invalid_external_json_falls_back(self):
        adapter = StaticLLMAdapter(
            LLMAdapterConfig(enabled=True, provider="openai_compatible", fallback_on_error=True),
            "not-json",
        )

        result = adapter.complete_json(
            system_prompt="Return JSON.",
            user_payload={"x": 1},
            fallback=lambda reason: {"fallback_reason": reason},
        )

        self.assertFalse(result.external_used)
        self.assertIn("did not contain", result.data["fallback_reason"])

    def test_fallback_can_be_disabled_for_debugging(self):
        adapter = StaticLLMAdapter(
            LLMAdapterConfig(enabled=True, provider="openai_compatible", fallback_on_error=False),
            "not-json",
        )

        with self.assertRaises(RuntimeError):
            adapter.complete_json(
                system_prompt="Return JSON.",
                user_payload={"x": 1},
                fallback=lambda reason: {"fallback_reason": reason},
            )


if __name__ == "__main__":
    unittest.main()
