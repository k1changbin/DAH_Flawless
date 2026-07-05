"""Policy update reviewers with external-LLM fallback.

The reviewer does not create attacks or defenses. It only judges bounded
policy-update candidates that were already produced by deterministic feedback
learners. If an external LLM is unavailable, invalid, or disabled, the
heuristic reviewer provides the same interface fully offline.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path
from typing import Any

from dah_flawless.schemas import decision

DEFAULT_SCALES = (1.0, 0.75, 0.5, 0.25, 0.0)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "policy_update_reviewer.json"


class PolicyUpdateReviewer:
    """Base interface for bounded policy update review."""

    name = "PolicyUpdateReviewer"

    def review_update(
        self,
        *,
        agent: str,
        update_name: str,
        before: dict,
        proposed: dict,
        context: dict,
    ) -> tuple[dict, dict]:
        raise NotImplementedError


class HeuristicPolicyUpdateReviewer(PolicyUpdateReviewer):
    """Offline reviewer that emulates the bounded LLM-review decision path."""

    name = "HeuristicPolicyUpdateReviewer"

    def __init__(
        self,
        *,
        scales: tuple[float, ...] = DEFAULT_SCALES,
        accept_threshold: float = 0.55,
        max_rejections: int = 3,
    ):
        self.scales = scales
        self.accept_threshold = accept_threshold
        self.max_rejections = max_rejections

    def review_update(
        self,
        *,
        agent: str,
        update_name: str,
        before: dict,
        proposed: dict,
        context: dict,
    ) -> tuple[dict, dict]:
        candidates = _build_candidates(before, proposed, self.scales)
        reviewed = [
            self._score_candidate(agent=agent, before=before, candidate=candidate, context=context)
            for candidate in candidates
        ]

        accepted = [candidate for candidate in reviewed if candidate["decision"] == "accept"]
        if accepted:
            selected = accepted[0]
            reason = "first_accepted_bounded_candidate"
        else:
            selected = max(reviewed, key=lambda item: item["review_score"])
            reason = "all_candidates_rejected_select_highest_score"

        log = decision(
            self.name,
            "policy_update_reviewed",
            reason,
            before={
                "agent": agent,
                "update_name": update_name,
                "policy_before": before,
                "policy_proposed": proposed,
                "context": context,
            },
            after={
                "selected_update": selected["value"],
                "selected_scale": selected["scale"],
                "review_score": selected["review_score"],
                "review_decision": selected["decision"],
                "rejection_count": sum(1 for item in reviewed if item["decision"] == "reject"),
                "max_rejections": self.max_rejections,
                "candidates": reviewed,
                "external_llm_used": False,
            },
        )
        return deepcopy(selected["value"]), log

    def _score_candidate(self, *, agent: str, before: dict, candidate: dict, context: dict) -> dict:
        value = candidate["value"]
        direction_score = _direction_score(agent, before, value, context)
        magnitude_score = _magnitude_score(before, value, context)
        score = round(0.65 * direction_score + 0.35 * magnitude_score, 4)
        result = dict(candidate)
        result["review_score"] = score
        result["decision"] = "accept" if score >= self.accept_threshold else "reject"
        result["reason"] = _reason_for_score(agent, score, direction_score, magnitude_score, context)
        return result


class ExternalLLMPolicyUpdateReviewer(PolicyUpdateReviewer):
    """OpenAI-compatible reviewer with mandatory offline fallback."""

    name = "ExternalLLMPolicyUpdateReviewer"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_s: float = 2.0,
        api_key: str = "EMPTY",
        fallback: PolicyUpdateReviewer | None = None,
        scales: tuple[float, ...] = DEFAULT_SCALES,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.api_key = api_key
        self.fallback = fallback or HeuristicPolicyUpdateReviewer(scales=scales)
        self.scales = scales

    def review_update(
        self,
        *,
        agent: str,
        update_name: str,
        before: dict,
        proposed: dict,
        context: dict,
    ) -> tuple[dict, dict]:
        fallback_value, fallback_log = self.fallback.review_update(
            agent=agent,
            update_name=update_name,
            before=before,
            proposed=proposed,
            context=context,
        )
        candidates = _build_candidates(before, proposed, self.scales)

        try:
            response = self._call_llm(agent, update_name, before, proposed, context, candidates)
            selected = _select_llm_candidate(response, candidates)
            if selected is None:
                raise ValueError("LLM selected no valid bounded candidate")
            log = decision(
                self.name,
                "policy_update_reviewed",
                "external_llm_selected_bounded_candidate",
                before={
                    "agent": agent,
                    "update_name": update_name,
                    "policy_before": before,
                    "policy_proposed": proposed,
                    "context": context,
                },
                after={
                    "selected_update": selected["value"],
                    "selected_scale": selected["scale"],
                    "review_score": response.get("score"),
                    "review_decision": response.get("decision"),
                    "reason": response.get("reason", ""),
                    "candidates": candidates,
                    "external_llm_used": True,
                    "fallback_log": fallback_log,
                },
            )
            return deepcopy(selected["value"]), log
        except Exception as exc:
            fallback_log = deepcopy(fallback_log)
            fallback_log["reason"] = "external_llm_unavailable_or_invalid_fallback"
            fallback_log["after"]["external_llm_used"] = False
            fallback_log["after"]["fallback_error"] = str(exc)
            fallback_log["after"]["fallback_reviewer"] = self.fallback.name
            return fallback_value, fallback_log

    def _call_llm(
        self,
        agent: str,
        update_name: str,
        before: dict,
        proposed: dict,
        context: dict,
        candidates: list[dict],
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You review bounded simulator policy updates. "
                        "Never create attacks, payloads, exploit steps, RF instructions, or API attack procedures. "
                        "Choose only one provided candidate scale. Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "agent": agent,
                            "update_name": update_name,
                            "before": before,
                            "proposed": proposed,
                            "context": context,
                            "candidate_scales": [candidate["scale"] for candidate in candidates],
                            "required_schema": {
                                "decision": "accept_or_reject",
                                "selected_scale": "one_of_candidate_scales",
                                "score": "0_to_1",
                                "reason": "brief_simulation_only_reason",
                            },
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            ],
            "temperature": 0.0,
            "max_tokens": 256,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc)) from exc

        content = body["choices"][0]["message"]["content"]
        return _parse_json_object(content)


def build_policy_update_reviewer(config_path: Path | None = None) -> PolicyUpdateReviewer:
    config = _load_config(config_path or DEFAULT_CONFIG_PATH)
    if os.getenv("DAH_POLICY_REVIEW_ENABLED"):
        config["enabled"] = os.getenv("DAH_POLICY_REVIEW_ENABLED", "").lower() in {"1", "true", "yes", "on"}
    if os.getenv("DAH_POLICY_REVIEW_PROVIDER"):
        config["provider"] = os.getenv("DAH_POLICY_REVIEW_PROVIDER")

    fallback = HeuristicPolicyUpdateReviewer(
        accept_threshold=float(config.get("accept_threshold", 0.55)),
        max_rejections=int(config.get("max_rejections", 3)),
    )
    if not config.get("enabled", False):
        return fallback
    if config.get("provider") != "openai_compatible":
        return fallback

    return ExternalLLMPolicyUpdateReviewer(
        base_url=os.getenv("DAH_LLM_BASE_URL", config.get("base_url", "http://127.0.0.1:8000/v1")),
        model=os.getenv("DAH_LLM_MODEL", config.get("model", "local-policy-reviewer")),
        timeout_s=float(os.getenv("DAH_LLM_TIMEOUT_S", config.get("timeout_s", 2))),
        api_key=os.getenv("DAH_LLM_API_KEY", config.get("api_key", "EMPTY")),
        fallback=fallback,
    )


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _build_candidates(before: dict, proposed: dict, scales: tuple[float, ...]) -> list[dict]:
    return [{"scale": scale, "value": _interpolate(before, proposed, scale)} for scale in scales]


def _interpolate(before: Any, proposed: Any, scale: float) -> Any:
    if isinstance(before, dict) and isinstance(proposed, dict):
        result = deepcopy(before)
        for key, proposed_value in proposed.items():
            if key in before:
                result[key] = _interpolate(before[key], proposed_value, scale)
            else:
                result[key] = deepcopy(proposed_value)
        return result
    if isinstance(before, (int, float)) and isinstance(proposed, (int, float)):
        value = before + (proposed - before) * scale
        if isinstance(before, int) and isinstance(proposed, int):
            return int(round(value))
        return round(value, 4)
    return deepcopy(proposed if scale > 0 else before)


def _direction_score(agent: str, before: dict, value: dict, context: dict) -> float:
    if agent == "RedAgent":
        return _red_direction_score(before, value, context)
    if agent == "BlueFeedbackLearner":
        return _blue_direction_score(before, value, context)
    return 0.7


def _red_direction_score(before: dict, value: dict, context: dict) -> float:
    detected = bool(context.get("detected", False))
    weight_delta = float(value.get("weight", 0.0)) - float(before.get("weight", 0.0))
    probe_delta = float(value.get("telemetry_probe_delta", 0.0)) - float(before.get("telemetry_probe_delta", 0.0))

    score = 0.5
    if detected and weight_delta <= 0:
        score += 0.25
    if (not detected) and weight_delta >= 0:
        score += 0.25
    if probe_delta == 0:
        score += 0.1
    elif detected and probe_delta <= 0:
        score += 0.15
    elif (not detected) and probe_delta >= 0:
        score += 0.15
    return min(1.0, score)


def _blue_direction_score(before: dict, value: dict, context: dict) -> float:
    domain = context.get("target_domain")
    if not domain:
        return 0.7
    score = 0.5
    sensitivity_delta = _nested_delta(before, value, "detection_sensitivity", domain)
    threshold_delta = _nested_delta(before, value, "escalation_threshold", domain)
    trust_delta = _nested_delta(before, value, "domain_trust", domain)

    missed = bool(context.get("attack_success", False)) and not bool(context.get("detection_success", False))
    false_positive = bool(context.get("false_positive", False))
    over_defense = bool(context.get("over_defense", False)) or context.get("winner") == "RED_ATTRITION"
    detected = bool(context.get("detection_success", False))

    if missed:
        if sensitivity_delta >= 0:
            score += 0.2
        if threshold_delta <= 0:
            score += 0.2
        if trust_delta <= 0:
            score += 0.1
    elif false_positive or over_defense:
        if sensitivity_delta <= 0:
            score += 0.2
        if threshold_delta >= 0:
            score += 0.2
        if trust_delta >= 0:
            score += 0.1
    elif detected:
        if abs(sensitivity_delta) <= 0.02:
            score += 0.2
        if abs(threshold_delta) <= 0.02:
            score += 0.15
        score += 0.1
    else:
        score += 0.1
    return min(1.0, score)


def _magnitude_score(before: dict, value: dict, context: dict) -> float:
    deltas = _flatten_numeric_deltas(before, value)
    if not deltas:
        return 1.0
    max_delta = max(abs(delta) for delta in deltas)
    if max_delta <= 0.03:
        return 1.0
    if max_delta <= 0.08:
        return 0.85
    if max_delta <= 0.5:
        return 0.75
    if max_delta <= 6.0 and context.get("agent_family") == "red_probe":
        return 0.75
    return 0.35


def _flatten_numeric_deltas(before: Any, value: Any) -> list[float]:
    if isinstance(before, dict) and isinstance(value, dict):
        deltas: list[float] = []
        for key in before:
            if key in value:
                deltas.extend(_flatten_numeric_deltas(before[key], value[key]))
        return deltas
    if isinstance(before, (int, float)) and isinstance(value, (int, float)):
        return [float(value) - float(before)]
    return []


def _nested_delta(before: dict, value: dict, group: str, key: str) -> float:
    return float(value.get(group, {}).get(key, 0.0)) - float(before.get(group, {}).get(key, 0.0))


def _reason_for_score(agent: str, score: float, direction_score: float, magnitude_score: float, context: dict) -> str:
    if score >= 0.55:
        return f"{agent} update is directionally consistent and bounded"
    if direction_score < 0.55:
        return f"{agent} update direction does not match scorer context"
    if magnitude_score < 0.55:
        return f"{agent} update magnitude is too large for bounded review"
    return f"{agent} update rejected by bounded reviewer"


def _parse_json_object(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not contain a JSON object")
    data = json.loads(text[start : end + 1])
    if data.get("decision") not in {"accept", "reject"}:
        raise ValueError("LLM response decision must be accept or reject")
    score = float(data.get("score", 0.0))
    if not 0.0 <= score <= 1.0:
        raise ValueError("LLM response score must be between 0 and 1")
    return data


def _select_llm_candidate(response: dict, candidates: list[dict]) -> dict | None:
    selected_scale = float(response.get("selected_scale", response.get("suggested_scale", 1.0)))
    for candidate in candidates:
        if abs(candidate["scale"] - selected_scale) < 1e-6:
            return candidate
    return None
