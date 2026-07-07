"""Dynamic round-level combat episodes.

This runner models one round as a variable-length Red/Blue interaction rather
than a single attack/detect/defend tick. Steps are decision events, not fixed
wall-clock seconds. Red and Blue may wait to conserve budgets, probe, drift,
inspect, defend, or terminate the round. The existing round simulator remains
the stable baseline; this module is the experimental combat loop.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

from dah_flawless.attacks.red_agent import RedAgent
from dah_flawless.blue.defense_planner import apply_defense_actions, plan_defense
from dah_flawless.blue.feedback_learner import (
    apply_blue_policy_state,
    apply_detection_policy,
    export_blue_policy_state,
    freeze_blue_policy,
    update_blue_policy,
)
from dah_flawless.blue.incident_report import write_incident_report
from dah_flawless.blue.mission_monitor import estimate_mission_risk
from dah_flawless.blue.threat_detection import detect_threats
from dah_flawless.config import (
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_ROUNDS,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_STEALTH_MODE,
    SCRIPTED_ATTACKS,
)
from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, write_jsonl
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.simulator import _advance_normal_state
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.observation import sync_external_observe_from_flat
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.reporting.frontend_log import write_frontend_combat_log
from dah_flawless.scoring.causal_consistency import assess_causal_consistency
from dah_flawless.scoring.metrics import summarize_logs
from dah_flawless.scoring.scorer import score_round
from dah_flawless.schemas import Attack, DefenseAction, Score, Threat, decision
from dah_flawless.situation_tagger import derive_tag_details

DEFAULT_MAX_COMBAT_STEPS = 100
DEFAULT_MIN_COMBAT_STEPS = 4
RED_ACTIONS = {
    "WAIT",
    "PROBE_BOUNDARY",
    "SLOW_DRIFT",
    "ESCALATE_MUTATION",
    "SWITCH_TACTIC",
    "FINALIZE_ATTACK",
    "ABORT",
}
BLUE_ACTIONS = {
    "WAIT",
    "PASSIVE_MONITOR",
    "INSPECT_INTERNAL",
    "RAISE_SUSPICION",
    "DEFEND",
    "DECLARE_STABLE",
}


@dataclass
class CombatStepMemory:
    last_suspicion: float = 0.0
    last_detected: bool = False
    last_recovered: bool = False
    last_effect_score: float = 0.0
    stable_steps: int = 0
    tactic_switches: int = 0
    active_strategy: str | None = None
    finalized: bool = False
    abort_requested: bool = False
    red_budget: float = 1.0
    blue_compute_budget: float = 1.0
    blue_power_budget: float = 1.0
    retry_attempts: int = 0
    finalize_attempts: int = 0
    low_budget_waits: int = 0
    recovery_streak: int = 0
    red_attack_cost_total: float = 0.0
    red_last_action_cost: float = 0.0
    red_mutation_steps: int = 0
    blue_defense_cost_total: float = 0.0
    blue_defense_steps: int = 0
    blue_consecutive_defense_steps: int = 0
    blue_defense_action_count: int = 0
    red_action_counts: dict[str, int] = field(default_factory=dict)
    blue_action_counts: dict[str, int] = field(default_factory=dict)

    def count_red(self, action: str) -> None:
        self.red_action_counts[action] = self.red_action_counts.get(action, 0) + 1

    def count_blue(self, action: str) -> None:
        self.blue_action_counts[action] = self.blue_action_counts.get(action, 0) + 1


class RoundCombatRunner:
    """Run variable-length round combat episodes."""

    def __init__(
        self,
        *,
        seed: int = DEFAULT_SEED,
        rounds: int = DEFAULT_ROUNDS,
        max_steps: int = DEFAULT_MAX_COMBAT_STEPS,
        min_steps: int = DEFAULT_MIN_COMBAT_STEPS,
        scenario: str = DEFAULT_SCENARIO,
        stealth_mode: str = DEFAULT_STEALTH_MODE,
        mutation_profile: str = DEFAULT_MUTATION_PROFILE,
        red_update_enabled: bool = True,
        blue_update_enabled: bool = True,
        red_policy_state: dict | None = None,
        blue_policy_state: dict | None = None,
        scripted_attacks: tuple[str, ...] = SCRIPTED_ATTACKS,
        policy_update_reviewer: PolicyUpdateReviewer | None = None,
    ):
        if rounds <= 0:
            raise ValueError("rounds must be > 0")
        if max_steps <= 0:
            raise ValueError("max_steps must be > 0")
        if min_steps <= 0:
            raise ValueError("min_steps must be > 0")
        if min_steps > max_steps:
            raise ValueError("min_steps must be <= max_steps")

        self.seed = seed
        self.rounds = rounds
        self.max_steps = max_steps
        self.min_steps = min_steps
        self.scenario = scenario
        self.stealth_mode = stealth_mode
        self.mutation_profile = mutation_profile
        self.red_update_enabled = red_update_enabled
        self.blue_update_enabled = blue_update_enabled
        self.red_policy_state = red_policy_state
        self.blue_policy_state = blue_policy_state
        self.scripted_attacks = scripted_attacks
        self.policy_update_reviewer = policy_update_reviewer or build_policy_update_reviewer()

    def run(
        self,
        *,
        log_path: Path | None = None,
        summary_path: Path | None = None,
        frontend_log_path: Path | None = None,
        initial_state: dict | None = None,
        previous_logs: list[dict] | None = None,
    ) -> tuple[list[dict], dict]:
        state = deepcopy(initial_state) if initial_state is not None else create_baseline_state(self.seed, self.scenario)
        if self.blue_policy_state is not None:
            apply_blue_policy_state(state, self.blue_policy_state)

        red_agent = RedAgent(
            self.seed,
            scripted_attacks=self.scripted_attacks,
            stealth_mode=self.stealth_mode,
            mutation_profile=self.mutation_profile,
            policy_state=self.red_policy_state,
            policy_update_reviewer=self.policy_update_reviewer,
        )
        logs: list[dict] = []
        previous_context = deepcopy(previous_logs or [])
        prev_hash = GENESIS_HASH
        history = make_history(state)

        for round_number in range(1, self.rounds + 1):
            state = _advance_normal_state(state, round_number)
            entry_without_hash, state, history = self._run_single_round(
                round_number=round_number,
                state=state,
                history=history,
                red_agent=red_agent,
                previous_logs=[*previous_context, *logs],
            )
            entry = attach_hash(prev_hash, entry_without_hash)
            logs.append(entry)
            prev_hash = entry["this_hash"]

        summary = summarize_logs(logs)
        summary.update(
            {
                "runner": "RoundCombatRunner",
                "rounds": self.rounds,
                "max_steps": self.max_steps,
                "min_steps": self.min_steps,
                "avg_step_count": round(mean(entry["step_count"] for entry in logs), 4) if logs else 0.0,
                "terminations": _count_by(logs, "termination_reason"),
                "red_step_actions": _count_step_actions(logs, "red_action"),
                "blue_step_actions": _count_step_actions(logs, "blue_action"),
                "scenario": state.get("scenario", self.scenario),
                "scenario_profile": deepcopy(state.get("scenario_profile", {})),
                "stealth_mode": self.stealth_mode,
                "mutation_profile": self.mutation_profile,
                "update_mode": {
                    "red_update_enabled": self.red_update_enabled,
                    "blue_update_enabled": self.blue_update_enabled,
                },
                "red_policy_state": red_agent.export_policy_state(),
                "blue_policy_state": export_blue_policy_state(state),
            }
        )

        if log_path is not None:
            write_jsonl(log_path, logs)
        if summary_path is not None:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            import json

            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        if frontend_log_path is not None:
            write_frontend_combat_log(frontend_log_path, logs, summary)
        return logs, summary

    def _run_single_round(
        self,
        *,
        round_number: int,
        state: dict,
        history: dict,
        red_agent: RedAgent,
        previous_logs: list[dict],
    ) -> tuple[dict, dict, dict]:
        redacted_for_red = redact_state(state)
        tag_details = derive_tag_details(redacted_for_red, history, redacted_for_red["capabilities"])
        red_tags = [detail.tag for detail in tag_details]
        attack, stealth, tactic, red_choice_log = red_agent.choose_attack(
            round_number,
            redacted_for_red,
            red_tags,
            tag_details,
            previous_logs=previous_logs,
        )
        red_goal = deepcopy(tactic.get("goal_plan") or red_choice_log.get("after", {}).get("goal"))

        combat_memory = CombatStepMemory(active_strategy=tactic.get("strategy"))
        current_state = deepcopy(state)
        last_attacked_state = deepcopy(state)
        recognized_threat_history: list[list[Threat]] = []
        recovery_history: list[dict[str, bool]] = []
        cumulative_actions: list[DefenseAction] = []
        step_logs: list[dict] = []
        episode_situation_tags: set[str] = set()
        episode_recognized_threats: list[Threat] = []
        final_score: Score | None = None
        final_report: dict | None = None
        final_causal: dict | None = None
        final_threats: list[Threat] = []
        final_risks = []
        final_actions: list[DefenseAction] = []
        final_decision_logs: list[dict] = []
        termination_reason = "max_steps"

        for step_number in range(1, self.max_steps + 1):
            red_action = _plan_red_step(step_number, combat_memory)
            red_state, red_step_log = _execute_red_step(
                current_state,
                attack=attack,
                base_tactic=tactic,
                red_action=red_action,
                memory=combat_memory,
            )
            combat_memory.count_red(red_action)
            if red_action in {"PROBE_BOUNDARY", "SLOW_DRIFT", "ESCALATE_MUTATION", "SWITCH_TACTIC"}:
                last_attacked_state = deepcopy(red_state)

            redacted_for_blue = redact_state(red_state)
            candidate_tags, candidate_threats, threat_log = detect_threats(
                redacted_for_blue,
                history,
                red_state["capabilities"],
            )
            candidate_threats, policy_detection_log = apply_detection_policy(
                candidate_threats,
                export_blue_policy_state(red_state),
            )
            suspicion = _max_confidence(candidate_threats)
            blue_action = _plan_blue_step(
                step_number=step_number,
                suspicion=suspicion,
                candidate_threats=candidate_threats,
                memory=combat_memory,
            )
            combat_memory.count_blue(blue_action)
            recognized_threats = _recognized_threats_for_action(blue_action, candidate_threats)
            episode_situation_tags.update(candidate_tags)
            episode_recognized_threats.extend(recognized_threats)
            risks, risk_log = estimate_mission_risk(redacted_for_blue, recognized_threats)
            post_blue_state = deepcopy(red_state)
            actions: list[DefenseAction] = []
            defense_log = _blue_idle_log(blue_action, recognized_threats, combat_memory)
            if blue_action == "DEFEND":
                actions, defense_log = plan_defense(
                    recognized_threats,
                    risks,
                    red_state["mission"],
                    red_state["defense_runtime"],
                )
                post_blue_state = apply_defense_actions(
                    red_state,
                    actions,
                    history,
                    recognized_threats,
                    red_state["capabilities"],
                )
                cumulative_actions.extend(actions)
                _record_blue_defense_pressure(post_blue_state, actions, combat_memory)
            else:
                _apply_blue_budget_cost(post_blue_state, blue_action, combat_memory)
                _record_blue_defense_pressure(post_blue_state, [], combat_memory)

            score = score_round(
                last_attacked_state,
                post_blue_state,
                attack,
                recognized_threats,
                actions,
                threat_history=recognized_threat_history,
                recovery_history=recovery_history,
                red_goal=red_goal,
            )
            causal_consistency, causal_log = assess_causal_consistency(
                attack=attack,
                red_goal=red_goal,
                red_tactic={**tactic, "strategy": combat_memory.active_strategy, "step_action": red_action},
                mutation_log=red_step_log,
                pre_attack_tags=red_tags,
                situation_tags=candidate_tags,
                threats=recognized_threats,
                score=score,
            )
            report, report_log = write_incident_report(recognized_threats, risks, cumulative_actions, score)

            detected_this_step = _detected_for_attack(attack, recognized_threats)
            current_recovery = bool(score.evidence.get("current_recovery_success", score.recovery_success))
            combat_memory.last_suspicion = suspicion
            combat_memory.last_detected = detected_this_step
            combat_memory.last_recovered = current_recovery
            combat_memory.last_effect_score = _effect_score(score)
            combat_memory.stable_steps = _next_stable_steps(combat_memory, red_action, suspicion, score)
            if red_action == "FINALIZE_ATTACK":
                combat_memory.finalized = True
            if red_action == "ABORT":
                combat_memory.abort_requested = True
            _update_red_retry_memory(combat_memory, red_action, detected_this_step, current_recovery)

            step_log = {
                "step": step_number,
                "red_action": red_action,
                "blue_action": blue_action,
                "attack": attack.to_dict(),
                "red_goal": deepcopy(red_goal),
                "red_tactic": {
                    "strategy": combat_memory.active_strategy,
                    "base_strategy": tactic.get("strategy"),
                    "mutation_profile": tactic.get("mutation_profile"),
                },
                "red_step": red_step_log,
                "blue_candidate_tags": candidate_tags,
                "blue_candidate_threats": [threat.to_dict() for threat in candidate_threats],
                "blue_recognized_threats": [threat.to_dict() for threat in recognized_threats],
                "blue_suspicion": suspicion,
                "detected_this_step": detected_this_step,
                "defense_actions": [action.to_dict() for action in actions],
                "step_score": score.to_dict(),
                "causal_consistency": causal_consistency,
                "budgets": _budget_snapshot(combat_memory),
                "stable_steps": combat_memory.stable_steps,
            }
            step_logs.append(step_log)
            final_score = score
            final_report = report
            final_causal = causal_consistency
            final_threats = recognized_threats
            final_risks = risks
            final_actions = list(cumulative_actions)
            final_decision_logs = [
                red_step_log,
                threat_log,
                policy_detection_log,
                risk_log,
                defense_log,
                report_log,
            ]

            termination_reason = _termination_reason(
                step_number=step_number,
                max_steps=self.max_steps,
                min_steps=self.min_steps,
                red_action=red_action,
                blue_action=blue_action,
                memory=combat_memory,
                score=score,
            )
            if termination_reason != "continue":
                break

            recognized_threat_history.append(recognized_threats)
            recovery_history.append({attack.target_domain: current_recovery})
            current_state = post_blue_state
            history = make_history(current_state)

        if final_score is None:
            raise RuntimeError("RoundCombatRunner produced no steps")

        combat_mutation_log = _aggregate_combat_mutation_log(step_logs)
        final_causal, final_causal_log = assess_causal_consistency(
            attack=attack,
            red_goal=red_goal,
            red_tactic={
                **tactic,
                "strategy": combat_memory.active_strategy,
                "combat_step_count": len(step_logs),
                "mutation_log_kind": "combat_episode_aggregate",
            },
            mutation_log=combat_mutation_log,
            pre_attack_tags=red_tags,
            situation_tags=sorted(episode_situation_tags),
            threats=episode_recognized_threats or final_threats,
            score=final_score,
        )
        final_decision_logs.insert(-1, final_causal_log)

        blue_policy_before = export_blue_policy_state(current_state)
        if self.blue_update_enabled:
            blue_policy_after, blue_update_log = update_blue_policy(
                blue_policy_before,
                final_score,
                final_threats,
                final_actions,
                reviewer=self.policy_update_reviewer,
            )
        else:
            blue_policy_after, blue_update_log = freeze_blue_policy(blue_policy_before)
        apply_blue_policy_state(current_state, blue_policy_after)

        if self.red_update_enabled:
            red_update_log = red_agent.update_weight(
                attack.name,
                final_score.detection_success,
                goal_id=(red_goal or {}).get("goal_id"),
                score=final_score,
                round_number=round_number,
            )
        else:
            red_update_log = decision(
                "RedAgent",
                "weight_update_skipped",
                "red_policy_frozen",
                before={"attack": attack.name, "detected": final_score.detection_success},
                after=red_agent.export_policy_state(),
            )

        entry_without_hash = {
            "round": round_number,
            "seed": self.seed,
            "runner": "RoundCombatRunner",
            "scenario": current_state.get("scenario", self.scenario),
            "scenario_profile": deepcopy(current_state.get("scenario_profile", {})),
            "mutation_profile": self.mutation_profile,
            "update_mode": {
                "red_update_enabled": self.red_update_enabled,
                "blue_update_enabled": self.blue_update_enabled,
            },
            "truth_model": "scorer_truth",
            "truth_storage_key": 'state["world"]',
            "raw_world_source_hash": current_state["world"].get("raw_world_hash"),
            "raw_world_feature_scores": deepcopy(current_state["world"].get("raw_world_feature_scores", {})),
            "attack": attack.to_dict(),
            "stealth": stealth,
            "red_goal": red_goal,
            "red_tactic": tactic,
            "red_situation_tags": red_tags,
            "red_situation_tag_details": [detail.to_dict() for detail in tag_details],
            "combat_steps": step_logs,
            "combat_mutation_log": combat_mutation_log,
            "step_count": len(step_logs),
            "max_steps": self.max_steps,
            "termination_reason": termination_reason,
            "red_step_action_counts": deepcopy(combat_memory.red_action_counts),
            "blue_step_action_counts": deepcopy(combat_memory.blue_action_counts),
            "threats": [threat.to_dict() for threat in final_threats],
            "mission_risks": [risk.to_dict() for risk in final_risks],
            "defense_actions": [action.to_dict() for action in final_actions],
            "score": final_score.to_dict(),
            "causal_consistency": final_causal,
            "incident_report": final_report,
            "red_policy_state": red_agent.export_policy_state(),
            "blue_policy_state": export_blue_policy_state(current_state),
            "feedback": {
                "red_policy_updated": self.red_update_enabled,
                "blue_policy_updated": self.blue_update_enabled,
                "winner": final_score.winner,
                "winner_side": final_score.winner_side,
                "winner_detail": final_score.winner_detail,
                "outcome_reason": final_score.outcome_reason,
                "target_domain": attack.target_domain,
                "goal_id": final_score.goal_id,
                "attack_success": final_score.attack_success,
                "goal_success": final_score.goal_success,
                "goal_reward": final_score.goal_reward,
                "mission_impact_score": final_score.evidence.get("mission_impact", {}).get("mission_impact_score"),
                "causal_consistency_score": final_causal["consistency_score"],
                "causal_consistency_status": final_causal["status"],
                "detection_success": final_score.detection_success,
                "recovery_success": final_score.recovery_success,
                "termination_reason": termination_reason,
            },
            "decision_log": [
                red_choice_log,
                *final_decision_logs,
                blue_update_log,
                red_update_log,
            ],
            "red_input_redacted": "world" not in redacted_for_red,
            "blue_input_redacted": "world" not in redact_state(current_state),
        }
        return entry_without_hash, current_state, make_history(current_state)


def run_combat_rounds(
    *,
    seed: int = DEFAULT_SEED,
    rounds: int = DEFAULT_ROUNDS,
    max_steps: int = DEFAULT_MAX_COMBAT_STEPS,
    min_steps: int = DEFAULT_MIN_COMBAT_STEPS,
    scenario: str = DEFAULT_SCENARIO,
    stealth_mode: str = DEFAULT_STEALTH_MODE,
    mutation_profile: str = DEFAULT_MUTATION_PROFILE,
    log_path: Path | None = None,
    summary_path: Path | None = None,
    frontend_log_path: Path | None = None,
) -> tuple[list[dict], dict]:
    runner = RoundCombatRunner(
        seed=seed,
        rounds=rounds,
        max_steps=max_steps,
        min_steps=min_steps,
        scenario=scenario,
        stealth_mode=stealth_mode,
        mutation_profile=mutation_profile,
    )
    return runner.run(log_path=log_path, summary_path=summary_path, frontend_log_path=frontend_log_path)


def _plan_red_step(step_number: int, memory: CombatStepMemory) -> str:
    if memory.red_budget < 0.08:
        if memory.low_budget_waits < 3:
            return "WAIT"
        return "ABORT"
    if step_number == 1:
        return "PROBE_BOUNDARY"
    if memory.finalized and memory.last_effect_score < 0.62:
        if memory.retry_attempts < 2 and memory.red_budget >= 0.12:
            return "SWITCH_TACTIC"
        if memory.low_budget_waits < 2:
            return "WAIT"
        return "ABORT"
    if memory.last_detected and memory.last_recovered:
        if memory.last_suspicion >= 0.84 and memory.retry_attempts < 2:
            return "WAIT"
        if memory.tactic_switches < 3 and memory.retry_attempts < 5:
            return "SWITCH_TACTIC"
        if memory.retry_attempts < 7 and memory.red_budget >= 0.14:
            return "SLOW_DRIFT"
        if step_number >= 12 and memory.last_effect_score < 0.22:
            return "ABORT"
    if memory.last_detected and memory.tactic_switches < 2 and memory.last_effect_score < 0.72:
        return "SWITCH_TACTIC"
    if memory.last_suspicion >= 0.84 and memory.last_effect_score < 0.50:
        return "WAIT"
    if step_number >= 4 and memory.last_effect_score >= 0.62:
        return "FINALIZE_ATTACK"
    if step_number >= 8 and memory.last_effect_score >= 0.42 and memory.last_suspicion < 0.72:
        return "FINALIZE_ATTACK"
    if memory.last_suspicion < 0.45:
        return "SLOW_DRIFT"
    if memory.last_suspicion < 0.72:
        return "ESCALATE_MUTATION"
    return "SLOW_DRIFT"


def _plan_blue_step(
    *,
    step_number: int,
    suspicion: float,
    candidate_threats: list[Threat],
    memory: CombatStepMemory,
) -> str:
    if memory.blue_compute_budget < 0.06 or memory.blue_power_budget < 0.06:
        return "WAIT"
    if memory.blue_consecutive_defense_steps >= 3 and memory.last_recovered and suspicion < 0.92:
        return "INSPECT_INTERNAL" if suspicion >= 0.68 else "PASSIVE_MONITOR"
    if memory.blue_defense_cost_total >= 0.36 and memory.last_effect_score < 0.35 and suspicion < 0.86:
        return "INSPECT_INTERNAL" if suspicion >= 0.55 else "WAIT"
    if memory.stable_steps >= 3 and suspicion < 0.45:
        return "DECLARE_STABLE"
    if not candidate_threats or suspicion < 0.35:
        return "WAIT"
    if suspicion < 0.55:
        return "PASSIVE_MONITOR"
    if suspicion < 0.72:
        return "INSPECT_INTERNAL"
    if suspicion < 0.86 and step_number < 3:
        return "RAISE_SUSPICION"
    return "DEFEND"


def _execute_red_step(
    state: dict,
    *,
    attack: Attack,
    base_tactic: dict,
    red_action: str,
    memory: CombatStepMemory,
) -> tuple[dict, dict]:
    next_state = deepcopy(state)
    before = _attack_snapshot(next_state, attack.name)
    changed_paths: list[str] = []
    requested_delta: Any = None
    applied_delta: Any = None
    budget_before = memory.red_budget
    action_cost = 0.0
    if memory.last_detected and memory.last_recovered and red_action in {
        "WAIT",
        "SWITCH_TACTIC",
        "SLOW_DRIFT",
        "ESCALATE_MUTATION",
    }:
        memory.retry_attempts += 1

    if red_action == "WAIT":
        _recover_red_budget(memory, 0.025)
        if budget_before < 0.14:
            memory.low_budget_waits += 1
    elif red_action == "ABORT":
        action_cost = 0.01
        memory.red_budget = max(0.0, round(memory.red_budget - action_cost, 4))
    elif red_action == "FINALIZE_ATTACK":
        action_cost = 0.015
        memory.red_budget = max(0.0, round(memory.red_budget - action_cost, 4))
        memory.finalize_attempts += 1
        memory.low_budget_waits = 0
    else:
        memory.low_budget_waits = 0
        if red_action == "SWITCH_TACTIC":
            memory.tactic_switches += 1
            memory.active_strategy = _next_strategy(attack.name, memory.active_strategy or base_tactic.get("strategy"))
        scale = _red_delta_scale(red_action, memory)
        requested_delta, applied_delta, changed_paths = _apply_incremental_mutation(
            next_state,
            attack_name=attack.name,
            strategy=memory.active_strategy or base_tactic.get("strategy"),
            scale=scale,
        )
        action_cost = round(_red_action_cost(red_action) * scale, 4)
        memory.red_budget = max(0.0, round(memory.red_budget - action_cost, 4))
        if changed_paths:
            memory.red_mutation_steps += 1

    memory.red_last_action_cost = round(action_cost, 4)
    memory.red_attack_cost_total = round(memory.red_attack_cost_total + action_cost, 4)
    next_state.setdefault("defense_runtime", {})["red_combat_pressure"] = {
        "current_action_cost": memory.red_last_action_cost,
        "round_attack_cost": memory.red_attack_cost_total,
        "mutation_steps": memory.red_mutation_steps,
        "red_budget_remaining": memory.red_budget,
    }

    after = _attack_snapshot(next_state, attack.name)
    sync_external_observe_from_flat(next_state["blue_observed"])
    return next_state, {
        "agent": "RedStepPlanner",
        "event": "combat_step_action",
        "reason": red_action,
        "attack": attack.name,
        "step_action": red_action,
        "strategy": memory.active_strategy or base_tactic.get("strategy"),
        "safety_boundary": "simulated external observe incremental mutation only",
        "requested_delta": requested_delta,
        "applied_delta": applied_delta,
        "changed_paths": changed_paths,
        "before": before,
        "after": after,
    }


def _apply_incremental_mutation(
    state: dict,
    *,
    attack_name: str,
    strategy: str | None,
    scale: float,
) -> tuple[Any, Any, list[str]]:
    obs = state["blue_observed"]
    if attack_name == "TELEMETRY_FDI":
        delta = round(1.2 * scale, 3)
        before = float(obs["telemetry"]["battery_percent"])
        obs["telemetry"]["battery_percent"] = round(min(100.0, before + delta), 3)
        if strategy in {"motor_status_masking", "internal_external_gap_shaping"} and scale >= 0.55:
            obs["telemetry"]["motor_status"] = "OK"
        if strategy == "confidence_spoofing":
            obs["telemetry"]["battery_drain_rate"] = round(max(0.2, float(obs["telemetry"].get("battery_drain_rate", 1.0)) - 0.08 * scale), 3)
        return delta, round(obs["telemetry"]["battery_percent"] - before, 3), ["telemetry.battery_percent"]

    if attack_name == "PRIORITY_POISONING":
        step_delta = round(0.042 * scale, 4)
        priorities = obs["mission"]["area_priority"]
        before = deepcopy(priorities)
        priorities["A"] = round(max(0.0, float(priorities.get("A", 0.0)) - step_delta), 4)
        priorities["C"] = round(min(1.0, float(priorities.get("C", 0.0)) + step_delta), 4)
        if strategy == "mission_confidence_shaping":
            priorities["B"] = round(max(0.0, float(priorities.get("B", 0.0)) - step_delta * 0.4), 4)
            priorities["C"] = round(min(1.0, float(priorities.get("C", 0.0)) + step_delta * 0.4), 4)
        if priorities["C"] >= priorities["A"] or strategy in {"recommended_area_nudge", "mission_confidence_shaping"}:
            obs["mission"]["recommended_area"] = "C"
        return (
            {"A": -step_delta, "C": step_delta},
            _priority_delta(before, priorities),
            ["mission.area_priority.A", "mission.area_priority.C", "mission.recommended_area"],
        )

    if attack_name == "TIME_DESYNC_REPLAY":
        sequence_delta = -max(1, int(round(scale)))
        timestamp_delta = -max(4, int(round(8 * scale)))
        ack_sequence_gap = 1
        ack_delay_delta = int(round(60 * scale))
        latency_delta = int(round(25 * scale))
        packet_loss_delta = 0.006 * scale
        jitter_delta = 0
        heartbeat_gap_delta = 0
        if strategy == "ack_confusion":
            ack_sequence_gap = max(1, int(round(2 * scale)))
            ack_delay_delta = int(round(280 * scale))
            latency_delta = int(round(45 * scale))
        elif strategy in {"delay", "selective_delay"}:
            timestamp_delta = -max(5, int(round(14 * scale)))
            latency_delta = int(round(180 * scale))
            jitter_delta = int(round(120 * scale))
        elif strategy == "selective_drop":
            packet_loss_delta = 0.035 * scale
            heartbeat_gap_delta = int(round(900 * scale))
            jitter_delta = int(round(100 * scale))
        elif strategy == "metadata_poisoning":
            sequence_delta = -1
            timestamp_delta = -max(4, int(round(6 * scale)))
            latency_delta = int(round(40 * scale))
        before = {
            "sequence_number": obs["c2_message"]["sequence_number"],
            "received_timestamp": obs["time"]["received_timestamp"],
            "ack_sequence_number": obs["c2_message"].get("ack", {}).get("sequence_number"),
            "latency_ms": obs["comms"].get("latency_ms"),
            "packet_loss": obs["comms"].get("packet_loss"),
            "ack_delay_ms": obs["comms"].get("ack_delay_ms"),
            "packet_interval_jitter_ms": obs["comms"].get("packet_interval_jitter_ms"),
            "heartbeat_gap_ms": obs["comms"].get("heartbeat_gap_ms"),
        }
        obs["c2_message"]["sequence_number"] = max(0, int(obs["c2_message"]["sequence_number"]) + sequence_delta)
        obs["time"]["received_timestamp"] = int(obs["time"]["received_timestamp"]) + timestamp_delta
        ack = obs["c2_message"].setdefault("ack", {})
        ack["visible"] = True
        ack["sequence_number"] = max(0, int(obs["c2_message"]["sequence_number"]) - ack_sequence_gap)
        ack["status"] = "ACCEPTED"
        obs["comms"]["ack_visible"] = True
        obs["comms"]["latency_ms"] = int(obs["comms"].get("latency_ms", 0)) + latency_delta
        obs["comms"]["packet_loss"] = round(min(1.0, float(obs["comms"].get("packet_loss", 0.0)) + packet_loss_delta), 4)
        obs["comms"]["ack_delay_ms"] = int(obs["comms"].get("ack_delay_ms", 0)) + ack_delay_delta
        obs["comms"]["packet_interval_jitter_ms"] = int(obs["comms"].get("packet_interval_jitter_ms", 0)) + jitter_delta
        obs["comms"]["heartbeat_gap_ms"] = int(obs["comms"].get("heartbeat_gap_ms", 0)) + heartbeat_gap_delta
        if strategy == "selective_drop":
            obs["comms"]["message_queue_depth"] = int(obs["comms"].get("message_queue_depth", 0)) + max(1, int(round(scale)))
        after = {
            "sequence_number": obs["c2_message"]["sequence_number"],
            "received_timestamp": obs["time"]["received_timestamp"],
            "ack_sequence_number": ack["sequence_number"],
            "latency_ms": obs["comms"].get("latency_ms"),
            "packet_loss": obs["comms"].get("packet_loss"),
            "ack_delay_ms": obs["comms"].get("ack_delay_ms"),
            "packet_interval_jitter_ms": obs["comms"].get("packet_interval_jitter_ms"),
            "heartbeat_gap_ms": obs["comms"].get("heartbeat_gap_ms"),
        }
        return (
            {"sequence_delta": sequence_delta, "timestamp_delta_s": timestamp_delta},
            _generic_delta(before, after),
            [
                "c2_message.sequence_number",
                "time.received_timestamp",
                "c2_message.ack.sequence_number",
                "comms.latency_ms",
                "comms.packet_loss",
                "comms.ack_delay_ms",
                "comms.packet_interval_jitter_ms",
                "comms.heartbeat_gap_ms",
            ],
        )

    return None, None, []


def _recognized_threats_for_action(blue_action: str, candidate_threats: list[Threat]) -> list[Threat]:
    if blue_action == "WAIT":
        return []
    if blue_action == "PASSIVE_MONITOR":
        return [threat for threat in candidate_threats if threat.confidence >= 0.90]
    return candidate_threats


def _blue_idle_log(blue_action: str, recognized_threats: list[Threat], memory: CombatStepMemory) -> dict:
    return decision(
        "BlueStepPlanner",
        "combat_step_action",
        blue_action.lower(),
        before=_budget_snapshot(memory),
        after={
            "blue_action": blue_action,
            "recognized_threats": [threat.to_dict() for threat in recognized_threats],
        },
    )


def _record_blue_defense_pressure(state: dict, actions: list[DefenseAction], memory: CombatStepMemory) -> None:
    action_cost = round(sum(float(action.availability_cost) for action in actions), 4)
    if actions:
        memory.blue_defense_cost_total = round(memory.blue_defense_cost_total + action_cost, 4)
        memory.blue_defense_steps += 1
        memory.blue_consecutive_defense_steps += 1
        memory.blue_defense_action_count += len(actions)
        compute_cost = action_cost * 0.55 + len(actions) * 0.006
        power_cost = action_cost * 0.35 + len(actions) * 0.004
        memory.blue_compute_budget = round(min(1.0, max(0.0, memory.blue_compute_budget - compute_cost + 0.004)), 4)
        memory.blue_power_budget = round(min(1.0, max(0.0, memory.blue_power_budget - power_cost + 0.003)), 4)
    else:
        memory.blue_consecutive_defense_steps = 0

    state.setdefault("defense_runtime", {})["combat_attrition"] = {
        "current_action_cost": action_cost,
        "round_defense_cost": memory.blue_defense_cost_total,
        "defense_steps": memory.blue_defense_steps,
        "consecutive_defense_steps": memory.blue_consecutive_defense_steps,
        "defense_action_count": memory.blue_defense_action_count,
        "red_current_action_cost": memory.red_last_action_cost,
        "red_round_attack_cost": memory.red_attack_cost_total,
        "red_mutation_steps": memory.red_mutation_steps,
        "red_budget_remaining": memory.red_budget,
    }


def _apply_blue_budget_cost(state: dict, blue_action: str, memory: CombatStepMemory) -> None:
    compute_cost, power_cost = {
        "WAIT": (0.0, 0.0),
        "PASSIVE_MONITOR": (0.01, 0.005),
        "INSPECT_INTERNAL": (0.035, 0.015),
        "RAISE_SUSPICION": (0.025, 0.012),
        "DECLARE_STABLE": (0.008, 0.004),
    }.get(blue_action, (0.02, 0.01))
    memory.blue_compute_budget = round(min(1.0, max(0.0, memory.blue_compute_budget - compute_cost + 0.006)), 4)
    memory.blue_power_budget = round(min(1.0, max(0.0, memory.blue_power_budget - power_cost + 0.004)), 4)
    state.setdefault("defense_runtime", {})["combat_budget"] = _budget_snapshot(memory)


def _termination_reason(
    *,
    step_number: int,
    max_steps: int,
    min_steps: int,
    red_action: str,
    blue_action: str,
    memory: CombatStepMemory,
    score: Score,
) -> str:
    if step_number < min_steps:
        return "continue"
    if red_action == "ABORT":
        return "red_abort"
    if score.winner == "RED_ATTRITION":
        return "red_attrition_success"
    if blue_action == "DECLARE_STABLE" and memory.stable_steps >= 3:
        return "blue_declared_stable"
    if red_action == "FINALIZE_ATTACK" and score.goal_success and not score.detection_success:
        return "red_finalized_undetected"
    if red_action == "FINALIZE_ATTACK" and score.detection_success and score.recovery_success:
        return "blue_recovered_final_attack"
    if red_action == "FINALIZE_ATTACK" and score.goal_success:
        return "red_finalized_detected"
    if red_action == "FINALIZE_ATTACK" and score.detection_success:
        return "blue_detected_final_attack"
    if red_action == "FINALIZE_ATTACK":
        return "red_finalized_no_effect"
    if step_number >= max_steps:
        return "max_steps"
    return "continue"


def _next_stable_steps(memory: CombatStepMemory, red_action: str, suspicion: float, score: Score) -> int:
    if red_action in {"WAIT", "ABORT"} and suspicion < 0.35 and not score.attack_success:
        return memory.stable_steps + 1
    return 0


def _update_red_retry_memory(
    memory: CombatStepMemory,
    red_action: str,
    detected_this_step: bool,
    current_recovery: bool,
) -> None:
    if detected_this_step and current_recovery:
        memory.recovery_streak += 1
    elif not current_recovery:
        memory.recovery_streak = 0
    if red_action in {"FINALIZE_ATTACK", "ABORT"}:
        return
    if memory.last_effect_score >= 0.62 and not detected_this_step:
        memory.retry_attempts = max(0, memory.retry_attempts - 1)


def _effect_score(score: Score) -> float:
    return float(score.evidence.get("goal_score", {}).get("effect_score", 0.0))


def _detected_for_attack(attack: Attack, threats: list[Threat]) -> bool:
    return any(threat.target == attack.target_domain and threat.confidence >= 0.60 for threat in threats)


def _max_confidence(threats: list[Threat]) -> float:
    return max((float(threat.confidence) for threat in threats), default=0.0)


def _red_delta_scale(red_action: str, memory: CombatStepMemory) -> float:
    base = {
        "PROBE_BOUNDARY": 0.35,
        "SLOW_DRIFT": 0.75,
        "SWITCH_TACTIC": 0.60,
        "ESCALATE_MUTATION": 1.35,
    }.get(red_action, 0.0)
    if memory.last_detected:
        base *= 0.55
    elif memory.last_suspicion >= 0.72:
        base *= 0.70
    return round(max(0.10, base), 4)


def _red_action_cost(red_action: str) -> float:
    return {
        "PROBE_BOUNDARY": 0.015,
        "SLOW_DRIFT": 0.025,
        "SWITCH_TACTIC": 0.035,
        "ESCALATE_MUTATION": 0.045,
    }.get(red_action, 0.0)


def _recover_red_budget(memory: CombatStepMemory, amount: float) -> None:
    memory.red_budget = round(min(1.0, memory.red_budget + amount), 4)


def _next_strategy(attack_name: str, current: str | None) -> str:
    strategies = {
        "TIME_DESYNC_REPLAY": ("timestamp_creep", "sequence_lag", "ack_confusion", "selective_delay"),
        "TELEMETRY_FDI": ("battery_slow_drift", "confidence_spoofing", "internal_external_gap_shaping"),
        "PRIORITY_POISONING": ("area_priority_drift", "recommended_area_nudge", "mission_confidence_shaping"),
    }.get(attack_name, ("generic_drift",))
    if current not in strategies:
        return strategies[0]
    return strategies[(strategies.index(current) + 1) % len(strategies)]


def _attack_snapshot(state: dict, attack_name: str) -> Any:
    obs = state["blue_observed"]
    if attack_name == "TELEMETRY_FDI":
        return {
            "battery_percent": obs["telemetry"]["battery_percent"],
            "motor_status": obs["telemetry"]["motor_status"],
        }
    if attack_name == "PRIORITY_POISONING":
        return deepcopy(obs["mission"]["area_priority"])
    if attack_name == "TIME_DESYNC_REPLAY":
        return {
            "sequence_number": obs["c2_message"]["sequence_number"],
            "received_timestamp": obs["time"]["received_timestamp"],
            "ack_sequence_number": obs["c2_message"].get("ack", {}).get("sequence_number"),
            "latency_ms": obs["comms"].get("latency_ms"),
            "packet_loss": obs["comms"].get("packet_loss"),
        }
    return None


def _priority_delta(before: dict, after: dict) -> dict:
    return {area: round(float(after.get(area, 0.0)) - float(value), 4) for area, value in before.items()}


def _generic_delta(before: Any, after: Any) -> Any:
    if isinstance(before, dict) and isinstance(after, dict):
        delta = {}
        for key in sorted(set(before).union(after)):
            value = _generic_delta(before.get(key), after.get(key))
            if value is not None:
                delta[key] = value
        return delta
    if isinstance(before, (int, float)) and isinstance(after, (int, float)) and not isinstance(before, bool):
        value = after - before
        return value if isinstance(before, int) and isinstance(after, int) else round(value, 4)
    if before != after:
        return after
    return None


def _budget_snapshot(memory: CombatStepMemory) -> dict[str, float]:
    return {
        "red_budget": memory.red_budget,
        "blue_compute_budget": memory.blue_compute_budget,
        "blue_power_budget": memory.blue_power_budget,
        "red_retry_attempts": memory.retry_attempts,
        "red_finalize_attempts": memory.finalize_attempts,
        "red_low_budget_waits": memory.low_budget_waits,
        "red_recovery_streak": memory.recovery_streak,
        "red_round_attack_cost": memory.red_attack_cost_total,
        "red_last_action_cost": memory.red_last_action_cost,
        "red_mutation_steps": memory.red_mutation_steps,
        "blue_round_defense_cost": memory.blue_defense_cost_total,
        "blue_defense_steps": memory.blue_defense_steps,
    }


def _aggregate_combat_mutation_log(step_logs: list[dict]) -> dict:
    changed_paths: set[str] = set()
    step_mutations: list[dict] = []
    for step in step_logs:
        red_step = step.get("red_step", {})
        step_paths = sorted(set(red_step.get("changed_paths", [])))
        if not step_paths:
            continue
        changed_paths.update(step_paths)
        step_mutations.append(
            {
                "step": step.get("step"),
                "red_action": step.get("red_action"),
                "strategy": red_step.get("strategy"),
                "changed_paths": step_paths,
                "requested_delta": deepcopy(red_step.get("requested_delta")),
                "applied_delta": deepcopy(red_step.get("applied_delta")),
            }
        )

    ordered_paths = sorted(changed_paths)
    return {
        "agent": "RedStepPlanner",
        "event": "combat_episode_mutation_summary",
        "reason": "aggregate_combat_step_mutations",
        "changed_paths": ordered_paths,
        "policy_decisions": [{"path": path, "approved": True} for path in ordered_paths],
        "step_mutations": step_mutations,
        "mutation_step_count": len(step_mutations),
    }


def _count_by(logs: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in logs:
        value = str(entry.get(key, "UNKNOWN"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_step_actions(logs: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in logs:
        for step in entry.get("combat_steps", []):
            value = str(step.get(key, "UNKNOWN"))
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
