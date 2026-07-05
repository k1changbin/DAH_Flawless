"""Causal consistency checks for simulator-only attack effects."""

from __future__ import annotations

from typing import Any

from dah_flawless.attacks.effect_contracts import get_attack_effect_contract, score_contract_alignment
from dah_flawless.schemas import Attack, Score, Threat, decision


def assess_causal_consistency(
    *,
    attack: Attack,
    red_goal: dict | None,
    red_tactic: dict | None,
    mutation_log: dict,
    pre_attack_tags: list[str],
    situation_tags: list[str],
    threats: list[Threat],
    score: Score,
) -> tuple[dict[str, Any], dict]:
    """Check attack -> mutation -> tag/effect -> scorer evidence alignment."""

    goal_id = (red_goal or {}).get("goal_id") or score.goal_id
    contract = get_attack_effect_contract(attack.name)
    alignment = score_contract_alignment(attack.name, red_goal or {"goal_id": goal_id})
    changed_paths = _changed_paths(mutation_log)
    observed_tags = set(pre_attack_tags) | set(situation_tags)
    threat_tags = _threat_tags(threats)
    goal_evidence = score.evidence.get("goal_score", {}).get("evidence", {})

    matched_paths = _matched_paths(changed_paths, contract.mutation_paths)
    matched_tags = sorted(set(contract.expected_tags).intersection(observed_tags))
    matched_effect_tags = sorted(set(contract.expected_effect_tags).intersection(threat_tags))
    matched_evidence = sorted(set(contract.success_evidence_keys).intersection(goal_evidence))

    violations: list[str] = []
    warnings: list[str] = []
    if not alignment["supported_goal"]:
        violations.append("unsupported_attack_goal_pair")
    if not matched_paths:
        violations.append("no_contract_mutation_path_changed")
    if score.goal_success and not matched_evidence:
        violations.append("goal_success_without_contract_evidence")
    if score.goal_success and not matched_tags:
        warnings.append("goal_success_without_expected_tags")
    if score.goal_success and not matched_effect_tags:
        warnings.append("goal_success_without_blue_effect_hypothesis")
    if score.goal_reward >= 0.70 and not alignment["supported_goal"]:
        violations.append("high_reward_on_unsupported_contract")

    path_component = 1.0 if matched_paths else 0.0
    tag_component = min(1.0, len(matched_tags) / max(1, min(3, len(contract.expected_tags))))
    evidence_component = min(1.0, len(matched_evidence) / max(1, min(2, len(contract.success_evidence_keys))))
    effect_component = 1.0 if matched_effect_tags else (0.55 if not score.goal_success else 0.0)
    support_component = 1.0 if alignment["supported_goal"] else 0.0
    consistency_score = round(
        0.30 * support_component
        + 0.25 * path_component
        + 0.20 * evidence_component
        + 0.15 * tag_component
        + 0.10 * effect_component,
        4,
    )
    if violations:
        status = "FAIL"
    elif warnings or consistency_score < 0.72:
        status = "WARN"
    else:
        status = "PASS"

    report = {
        "status": status,
        "consistency_score": consistency_score,
        "attack": attack.name,
        "goal_id": goal_id,
        "strategy": (red_tactic or {}).get("strategy"),
        "contract_supported": bool(alignment["supported_goal"]),
        "contract_reason": alignment["reason"],
        "changed_paths": changed_paths,
        "matched_mutation_paths": matched_paths,
        "matched_tags": matched_tags,
        "matched_effect_tags": matched_effect_tags,
        "matched_evidence_keys": matched_evidence,
        "violations": violations,
        "warnings": warnings,
        "causal_chain": [
            "attack_contract",
            "observe_mutation",
            "situation_tags",
            "blue_effect_hypothesis",
            "goal_scorer_evidence",
        ],
    }
    log = decision(
        "CausalConsistencyMonitor",
        "causal_chain_checked",
        status.lower(),
        before={
            "attack": attack.name,
            "goal_id": goal_id,
            "strategy": (red_tactic or {}).get("strategy"),
        },
        after=report,
    )
    return report, log


def _changed_paths(mutation_log: dict) -> list[str]:
    paths = []
    for item in mutation_log.get("policy_decisions", []):
        path = item.get("path")
        if path and item.get("approved", True):
            paths.append(path)
    return sorted(set(paths))


def _matched_paths(changed_paths: list[str], expected_paths: tuple[str, ...]) -> list[str]:
    matched = []
    for changed in changed_paths:
        for expected in expected_paths:
            if changed == expected or changed.startswith(f"{expected}.") or expected.startswith(f"{changed}."):
                matched.append(changed)
                break
    return sorted(set(matched))


def _threat_tags(threats: list[Threat]) -> set[str]:
    tags: set[str] = set()
    for threat in threats:
        tags.update(threat.tags)
    return tags
