"""Reviewer-only gate for simulated observe mutations.

The reviewer never selects attacks, writes simulator state directly, or creates
real RF/API/payload instructions. It can only choose a bounded candidate between
the pre-mutation observe and the deterministic-policy-clamped observe.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from dah_flawless.llm import LLMAdapterConfig, LLMJsonAdapter, LLMJsonResult
from dah_flawless.schemas import decision

DEFAULT_SCALES = (1.0, 0.75, 0.5, 0.25, 0.0)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "mutation_approval_reviewer.json"
REVIEW_METADATA_ALLOWLIST = {
    "c2_message.ack.visible",
    "c2_message.ack.status",
    "comms.ack_visible",
}


class MutationApprovalReviewer:
    """Base interface for reviewer-only mutation approval."""

    name = "MutationApprovalReviewer"

    def review_mutation(
        self,
        *,
        attack_name: str,
        profile: str,
        tactic: dict,
        before_observe: dict,
        proposed_observe: dict,
        outcome: Any,
    ) -> tuple[dict, dict]:
        raise NotImplementedError


class HeuristicMutationApprovalReviewer(MutationApprovalReviewer):
    """Offline mutation reviewer that enforces the same bounded contract."""

    name = "HeuristicMutationApprovalReviewer"

    def __init__(self, *, scales: tuple[float, ...] = DEFAULT_SCALES):
        self.scales = scales

    def review_mutation(
        self,
        *,
        attack_name: str,
        profile: str,
        tactic: dict,
        before_observe: dict,
        proposed_observe: dict,
        outcome: Any,
    ) -> tuple[dict, dict]:
        changed_paths = _changed_paths(before_observe, proposed_observe)
        review = _heuristic_review_data(
            attack_name=attack_name,
            profile=profile,
            changed_paths=changed_paths,
            before_observe=before_observe,
            proposed_observe=proposed_observe,
            outcome=outcome,
        )
        selected = _interpolate_observe(before_observe, proposed_observe, float(review["selected_scale"]))
        log = _review_log(
            self.name,
            "heuristic_mutation_review",
            attack_name,
            profile,
            tactic,
            changed_paths,
            outcome,
            review,
            external_used=False,
        )
        return selected, log


class ExternalLLMMutationApprovalReviewer(MutationApprovalReviewer):
    """OpenAI-compatible mutation reviewer with mandatory local fallback."""

    name = "ExternalLLMMutationApprovalReviewer"

    def __init__(
        self,
        *,
        fallback: MutationApprovalReviewer | None = None,
        llm_adapter: LLMJsonAdapter | None = None,
        scales: tuple[float, ...] = DEFAULT_SCALES,
    ):
        self.fallback = fallback or HeuristicMutationApprovalReviewer(scales=scales)
        self.scales = scales
        self.llm_adapter = llm_adapter or LLMJsonAdapter(
            LLMAdapterConfig(enabled=True, model="local-mutation-approval-reviewer"),
            role_name="mutation_approval_reviewer",
        )

    def review_mutation(
        self,
        *,
        attack_name: str,
        profile: str,
        tactic: dict,
        before_observe: dict,
        proposed_observe: dict,
        outcome: Any,
    ) -> tuple[dict, dict]:
        changed_paths = _changed_paths(before_observe, proposed_observe)
        hard_reject = _hard_reject_reason(changed_paths, before_observe, proposed_observe, outcome)
        if hard_reject:
            review = _reject_review(hard_reject, changed_paths)
            selected = _interpolate_observe(before_observe, proposed_observe, 0.0)
            log = _review_log(
                self.name,
                "deterministic_policy_reject",
                attack_name,
                profile,
                tactic,
                changed_paths,
                outcome,
                review,
                external_used=False,
            )
            return selected, log

        fallback_value, fallback_log = self.fallback.review_mutation(
            attack_name=attack_name,
            profile=profile,
            tactic=tactic,
            before_observe=before_observe,
            proposed_observe=proposed_observe,
            outcome=outcome,
        )
        result = self._complete_llm_review(attack_name, profile, tactic, changed_paths, outcome)

        if result.external_used:
            review = result.data
            selected = _interpolate_observe(before_observe, proposed_observe, float(review["selected_scale"]))
            log = _review_log(
                self.name,
                "external_llm_mutation_review",
                attack_name,
                profile,
                tactic,
                changed_paths,
                outcome,
                review,
                external_used=True,
                llm_provider=result.provider,
                llm_role=result.role_name,
                fallback_log=fallback_log,
            )
            return selected, log

        fallback_log = deepcopy(fallback_log)
        fallback_log["reason"] = "external_llm_unavailable_or_invalid_fallback"
        fallback_log["after"]["external_llm_used"] = False
        fallback_log["after"]["fallback_error"] = result.fallback_reason
        fallback_log["after"]["fallback_reviewer"] = self.fallback.name
        fallback_log["after"]["llm_role"] = result.role_name
        return fallback_value, fallback_log

    def _complete_llm_review(
        self,
        attack_name: str,
        profile: str,
        tactic: dict,
        changed_paths: list[str],
        outcome: Any,
    ) -> LLMJsonResult:
        return self.llm_adapter.complete_json(
            system_prompt=(
                "You review simulated observe mutations for a Red/Blue safety simulation. "
                "You may only approve, clamp to a provided scale, or reject. "
                "Never create attacks, payloads, exploit steps, RF instructions, or API attack procedures. "
                "Never increase mutation amplitude or add fields. Return JSON only."
            ),
            user_payload={
                "attack_name": attack_name,
                "profile": profile,
                "tactic": _redact_tactic_for_review(tactic),
                "changed_paths": changed_paths,
                "policy_decisions": _policy_decisions(outcome),
                "requested_delta": getattr(outcome, "requested_delta", None),
                "applied_delta_after_deterministic_policy": getattr(outcome, "applied_delta", None),
                "candidate_scales": list(self.scales),
                "required_schema": {
                    "action": "approve_or_clamp_or_reject",
                    "selected_scale": "one_of_candidate_scales",
                    "score": "0_to_1",
                    "reason": "brief_simulation_only_reason",
                    "allowed_fields": "list_of_changed_paths_or_policy_paths",
                    "safety_boundary": "no_real_rf_api_payload_or_exploit_instruction",
                },
            },
            fallback=lambda reason: {},
            validator=lambda data: _validate_llm_review_response(data, self.scales),
            temperature=0.0,
            max_tokens=320,
        )


def build_mutation_approval_reviewer(config_path: Path | None = None) -> MutationApprovalReviewer:
    config = _load_config(config_path or DEFAULT_CONFIG_PATH)
    fallback = HeuristicMutationApprovalReviewer()
    llm_config = LLMAdapterConfig.from_mapping(
        config,
        enabled_env="DAH_MUTATION_REVIEW_ENABLED",
        provider_env="DAH_MUTATION_REVIEW_PROVIDER",
        base_url_env="DAH_MUTATION_REVIEW_BASE_URL",
        model_env="DAH_MUTATION_REVIEW_MODEL",
        api_key_env="DAH_MUTATION_REVIEW_API_KEY",
        timeout_env="DAH_MUTATION_REVIEW_TIMEOUT_S",
    )
    if not llm_config.enabled or llm_config.provider != "openai_compatible":
        return fallback
    return ExternalLLMMutationApprovalReviewer(
        fallback=fallback,
        llm_adapter=LLMJsonAdapter(llm_config, role_name="mutation_approval_reviewer"),
    )


def _load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _review_log(
    agent: str,
    reason: str,
    attack_name: str,
    profile: str,
    tactic: dict,
    changed_paths: list[str],
    outcome: Any,
    review: dict,
    *,
    external_used: bool,
    llm_provider: str | None = None,
    llm_role: str | None = None,
    fallback_log: dict | None = None,
) -> dict:
    after = {
        "action": review["action"],
        "selected_scale": review["selected_scale"],
        "score": review["score"],
        "reason": review["reason"],
        "allowed_fields": review.get("allowed_fields", []),
        "safety_boundary": review.get("safety_boundary", ""),
        "external_llm_used": external_used,
        "reviewed_changed_paths": changed_paths,
    }
    if llm_provider:
        after["llm_provider"] = llm_provider
    if llm_role:
        after["llm_role"] = llm_role
    if fallback_log:
        after["fallback_log"] = fallback_log

    return decision(
        agent,
        "mutation_approval_reviewed",
        reason,
        before={
            "attack_name": attack_name,
            "profile": profile,
            "tactic": _redact_tactic_for_review(tactic),
            "changed_paths": changed_paths,
            "policy_decisions": _policy_decisions(outcome),
        },
        after=after,
    )


def _heuristic_review_data(
    *,
    attack_name: str,
    profile: str,
    changed_paths: list[str],
    before_observe: dict,
    proposed_observe: dict,
    outcome: Any,
    fallback_reason: str | None = None,
) -> dict:
    hard_reject = _hard_reject_reason(changed_paths, before_observe, proposed_observe, outcome)
    if hard_reject:
        return _reject_review(hard_reject, changed_paths)

    clamped_count = sum(1 for item in _policy_decisions(outcome) if item.get("action") == "clamped")
    reason = "deterministic_policy_approved_simulated_observe_mutation"
    score = 0.88
    if clamped_count:
        reason = "deterministic_policy_already_clamped_before_reviewer"
        score = 0.82
    if fallback_reason:
        reason = f"{reason}; fallback_reason={fallback_reason}"

    return {
        "action": "approve",
        "selected_scale": 1.0,
        "score": score,
        "reason": f"{attack_name}:{reason}",
        "allowed_fields": sorted(_covered_changed_paths(changed_paths, _policy_paths(outcome))),
        "safety_boundary": f"profile={profile}; simulated external_observe mutation only",
    }


def _reject_review(reason: str, changed_paths: list[str]) -> dict:
    return {
        "action": "reject",
        "selected_scale": 0.0,
        "score": 0.0,
        "reason": reason,
        "allowed_fields": [],
        "safety_boundary": "deterministic policy wins; rejected mutation is reverted to pre-mutation observe",
    }


def _hard_reject_reason(changed_paths: list[str], before_observe: dict, proposed_observe: dict, outcome: Any) -> str | None:
    rejected_policy_paths = [
        item.get("path")
        for item in _policy_decisions(outcome)
        if not item.get("approved", False) and _decision_path_changed(item, changed_paths)
    ]
    if rejected_policy_paths:
        return f"deterministic_policy_rejected:{','.join(sorted(map(str, rejected_policy_paths)))}"

    forbidden = [path for path in changed_paths if _is_forbidden_path(path)]
    if forbidden:
        return f"forbidden_observe_scope:{','.join(forbidden)}"

    forbidden_transitions = [
        path for path in changed_paths if _is_forbidden_true_transition(path, before_observe, proposed_observe)
    ]
    if forbidden_transitions:
        return f"forbidden_success_transition:{','.join(forbidden_transitions)}"

    covered = _policy_paths(outcome)
    uncovered = [
        path
        for path in changed_paths
        if not _is_covered_changed_path(path, covered)
    ]
    if uncovered:
        return f"unreviewed_mutation_field:{','.join(uncovered)}"
    return None


def _decision_path_changed(decision_item: dict, changed_paths: list[str]) -> bool:
    path = decision_item.get("path")
    if not path:
        return True
    return any(_normalize_observe_path(changed) == path or _normalize_observe_path(changed).startswith(f"{path}.") for changed in changed_paths)


def _policy_paths(outcome: Any) -> set[str]:
    return {str(item.get("path")) for item in _policy_decisions(outcome) if item.get("path")}


def _policy_decisions(outcome: Any) -> list[dict]:
    return list(getattr(outcome, "policy_decisions", []) or [])


def _is_forbidden_path(path: str) -> bool:
    normalized = _normalize_observe_path(path)
    return normalized.startswith("internal_observe.") or normalized.startswith("state.world.") or normalized.startswith("raw_world.")


def _is_forbidden_true_transition(path: str, before_observe: dict, proposed_observe: dict) -> bool:
    if not (path.endswith(".auth_valid") or path.endswith(".signature_present") or path.endswith(".payload_visible")):
        return False
    before = _get_path(before_observe, path)
    proposed = _get_path(proposed_observe, path)
    return before is False and proposed is True


def _covered_changed_paths(changed_paths: list[str], policy_paths: set[str]) -> set[str]:
    return {path for path in changed_paths if _is_covered_changed_path(path, policy_paths)}


def _is_covered_changed_path(path: str, policy_paths: set[str]) -> bool:
    normalized = _normalize_observe_path(path)
    if normalized in REVIEW_METADATA_ALLOWLIST:
        return True
    return any(normalized == policy_path or normalized.startswith(f"{policy_path}.") for policy_path in policy_paths)


def _normalize_observe_path(path: str) -> str:
    normalized = path
    if normalized.startswith("blue_observed.external_observe."):
        normalized = normalized[len("blue_observed.external_observe.") :]
    for prefix in ("blue_observed.", "external_observe."):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    return normalized


def _validate_llm_review_response(data: dict, scales: tuple[float, ...]) -> None:
    action = data.get("action")
    if action not in {"approve", "clamp", "reject"}:
        raise ValueError("LLM response action must be approve, clamp, or reject")
    selected_scale = float(data.get("selected_scale", 1.0))
    if not any(abs(selected_scale - scale) < 1e-6 for scale in scales):
        raise ValueError("LLM selected no valid bounded mutation scale")
    score = float(data.get("score", 0.0))
    if not 0.0 <= score <= 1.0:
        raise ValueError("LLM response score must be between 0 and 1")
    if action == "approve" and selected_scale != 1.0:
        raise ValueError("approve must select scale 1.0")
    if action == "clamp" and selected_scale not in {0.75, 0.5, 0.25}:
        raise ValueError("clamp must select a partial scale")
    if action == "reject" and selected_scale != 0.0:
        raise ValueError("reject must select scale 0.0")


def _changed_paths(before: Any, after: Any, prefix: str = "") -> list[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        paths: list[str] = []
        for key in sorted(set(before).union(after)):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_changed_paths(before.get(key), after.get(key), child_prefix))
        return paths
    if before != after:
        return [prefix]
    return []


def _interpolate_observe(before: Any, proposed: Any, scale: float) -> Any:
    if isinstance(before, dict) and isinstance(proposed, dict):
        result = deepcopy(before)
        for key, proposed_value in proposed.items():
            if key in before:
                result[key] = _interpolate_observe(before[key], proposed_value, scale)
            elif scale >= 1.0:
                result[key] = deepcopy(proposed_value)
        return result
    if _is_number(before) and _is_number(proposed):
        value = before + (proposed - before) * scale
        if isinstance(before, int) and isinstance(proposed, int):
            return int(round(value))
        return round(value, 4)
    if scale >= 1.0:
        return deepcopy(proposed)
    return deepcopy(before)


def _get_path(root: dict, path: str) -> Any:
    node: Any = root
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _redact_tactic_for_review(tactic: dict) -> dict:
    redacted = deepcopy(tactic or {})
    redacted.pop("candidate_scores", None)
    redacted.pop("score_breakdown", None)
    redacted.pop("params_by_profile", None)
    return redacted
