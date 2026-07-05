"""Round-based Red/Blue simulation orchestrator."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Optional

from dah_flawless.attacks.mutations import apply_attack
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
    ACTIVE_DEFENSE_RECOVERY_PENALTY,
    AVAILABILITY_RECOVERY_PER_ROUND,
    DEFAULT_ROUNDS,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_STEALTH_MODE,
    ROUND_SECONDS,
    TRUST_BUDGET_RECOVERY_PER_ROUND,
)
from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, write_jsonl
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.mutation_review import MutationApprovalReviewer, build_mutation_approval_reviewer
from dah_flawless.observation import refresh_internal_observe_from_truth, sync_external_observe_from_flat
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.scoring.metrics import summarize_logs
from dah_flawless.scoring.scorer import score_round
from dah_flawless.schemas import decision
from dah_flawless.situation_tagger import derive_tag_details


def run_simulation(
    seed: int = DEFAULT_SEED,
    rounds: int = DEFAULT_ROUNDS,
    log_path: Optional[Path] = None,
    summary_path: Optional[Path] = None,
    scenario: str = DEFAULT_SCENARIO,
    stealth_mode: str = DEFAULT_STEALTH_MODE,
    mutation_profile: str = DEFAULT_MUTATION_PROFILE,
    initial_state: dict | None = None,
    red_update_enabled: bool = True,
    blue_update_enabled: bool = True,
    red_policy_state: dict | None = None,
    blue_policy_state: dict | None = None,
    previous_logs: list[dict] | None = None,
    policy_update_reviewer: PolicyUpdateReviewer | None = None,
    mutation_approval_reviewer: MutationApprovalReviewer | None = None,
) -> tuple[list[dict], dict]:
    state = deepcopy(initial_state) if initial_state is not None else create_baseline_state(seed, scenario)
    if blue_policy_state is not None:
        apply_blue_policy_state(state, blue_policy_state)
    scenario_label = state.get("scenario", scenario)
    history = make_history(state)
    reviewer = policy_update_reviewer or build_policy_update_reviewer()
    mutation_reviewer = mutation_approval_reviewer or build_mutation_approval_reviewer()
    red_agent = RedAgent(
        seed,
        stealth_mode=stealth_mode,
        mutation_profile=mutation_profile,
        policy_state=red_policy_state,
        policy_update_reviewer=reviewer,
    )
    logs: list[dict] = []
    historical_logs = deepcopy(previous_logs or [])
    threat_history: list[list] = []
    recovery_history: list[dict[str, bool]] = []
    prev_hash = GENESIS_HASH

    for round_number in range(1, rounds + 1):
        state = _advance_normal_state(state, round_number)
        redacted_for_red = redact_state(state)
        pre_attack_tag_details = derive_tag_details(redacted_for_red, history, redacted_for_red["capabilities"])
        pre_attack_tags = [detail.tag for detail in pre_attack_tag_details]
        attack, stealth, red_tactic, red_choice_log = red_agent.choose_attack(
            round_number,
            redacted_for_red,
            pre_attack_tags,
            pre_attack_tag_details,
            previous_logs=historical_logs + logs,
        )

        attacked_state, mutation_log = apply_attack(
            state,
            attack,
            stealth=stealth,
            tactic=red_tactic,
            mutation_approval_reviewer=mutation_reviewer,
        )
        pre_defense_state = deepcopy(attacked_state)

        redacted_for_blue = redact_state(attacked_state)
        situation_tags, threats, threat_log = detect_threats(
            redacted_for_blue, history, attacked_state["capabilities"]
        )
        threats, blue_detection_policy_log = apply_detection_policy(threats, export_blue_policy_state(attacked_state))
        risks, risk_log = estimate_mission_risk(redacted_for_blue, threats)
        actions, defense_log = plan_defense(threats, risks, attacked_state["mission"], attacked_state["defense_runtime"])
        blue_policy_before_round = export_blue_policy_state(attacked_state)
        defended_state = apply_defense_actions(attacked_state, actions, history, threats, attacked_state["capabilities"])
        if not blue_update_enabled:
            apply_blue_policy_state(defended_state, blue_policy_before_round)
        red_goal = deepcopy(red_tactic.get("goal_plan") or red_choice_log.get("after", {}).get("goal"))
        score = score_round(
            pre_defense_state,
            defended_state,
            attack,
            threats,
            actions,
            threat_history=threat_history,
            recovery_history=recovery_history,
            red_goal=red_goal,
        )
        report, report_log = write_incident_report(threats, risks, actions, score)
        if blue_update_enabled:
            blue_policy_after, blue_update_log = update_blue_policy(
                export_blue_policy_state(defended_state),
                score,
                threats,
                actions,
                reviewer=reviewer,
            )
        else:
            blue_policy_after, blue_update_log = freeze_blue_policy(blue_policy_before_round)
        apply_blue_policy_state(defended_state, blue_policy_after)
        if red_update_enabled:
            red_update_log = red_agent.update_weight(
                attack.name,
                score.detection_success,
                goal_id=(red_goal or {}).get("goal_id"),
                score=score,
                round_number=round_number,
            )
        else:
            red_update_log = decision(
                "RedAgent",
                "weight_update_skipped",
                "red_policy_frozen",
                before={"attack": attack.name, "detected": score.detection_success},
                after=red_agent.export_policy_state(),
            )

        entry_without_hash = {
            "round": round_number,
            "seed": seed,
            "scenario": scenario_label,
            "mutation_profile": mutation_profile,
            "update_mode": {
                "red_update_enabled": red_update_enabled,
                "blue_update_enabled": blue_update_enabled,
            },
            "truth_model": "scorer_truth",
            "truth_storage_key": 'state["world"]',
            "raw_world_source_hash": state["world"].get("raw_world_hash"),
            "raw_world_feature_scores": deepcopy(state["world"].get("raw_world_feature_scores", {})),
            "red_situation_tags": pre_attack_tags,
            "red_situation_tag_details": [detail.to_dict() for detail in pre_attack_tag_details],
            "situation_tags": situation_tags,
            "attack": attack.to_dict(),
            "stealth": stealth,
            "red_goal": red_goal,
            "red_tactic": red_tactic,
            "threats": [threat.to_dict() for threat in threats],
            "mission_risks": [risk.to_dict() for risk in risks],
            "defense_actions": defended_state["defense_runtime"]["active_defenses"],
            "score": score.to_dict(),
            "incident_report": report,
            "red_policy_state": red_agent.export_policy_state(),
            "blue_policy_state": export_blue_policy_state(defended_state),
            "feedback": {
                "red_policy_updated": red_update_enabled,
                "blue_policy_updated": blue_update_enabled,
                "winner": score.winner,
                "target_domain": attack.target_domain,
                "goal_id": score.goal_id,
                "attack_success": score.attack_success,
                "goal_success": score.goal_success,
                "goal_reward": score.goal_reward,
                "detection_success": score.detection_success,
                "recovery_success": score.recovery_success,
            },
            "decision_log": [
                red_choice_log,
                mutation_log,
                threat_log,
                blue_detection_policy_log,
                risk_log,
                defense_log,
                report_log,
                blue_update_log,
                red_update_log,
            ],
            "red_input_redacted": "world" not in redacted_for_red,
            "blue_input_redacted": "world" not in redacted_for_blue,
        }
        entry = attach_hash(prev_hash, entry_without_hash)
        logs.append(entry)
        prev_hash = entry["this_hash"]
        threat_history.append(threats)
        recovery_history.append(
            {attack.target_domain: bool(score.evidence.get("current_recovery_success", score.recovery_success))}
        )

        state = defended_state
        history = make_history(state)

    summary = summarize_logs(logs)
    summary["scenario"] = scenario_label
    summary["stealth_mode"] = stealth_mode
    summary["mutation_profile"] = mutation_profile
    summary["update_mode"] = {
        "red_update_enabled": red_update_enabled,
        "blue_update_enabled": blue_update_enabled,
    }
    summary["red_policy_state"] = red_agent.export_policy_state()
    summary["blue_policy_state"] = export_blue_policy_state(state)
    if state["world"].get("raw_world_hash"):
        summary["raw_world_source_hash"] = state["world"]["raw_world_hash"]
    if log_path is not None:
        write_jsonl(log_path, logs)
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return logs, summary


def _advance_normal_state(state: dict, round_number: int) -> dict:
    next_state = deepcopy(state)
    next_state["round"] = round_number
    if round_number > 1:
        _recover_operational_budget(next_state)
    next_state["world"]["time"]["round"] = round_number
    next_state["world"]["time"]["true_timestamp"] += ROUND_SECONDS
    next_state["world"]["command"]["expected_sequence_number"] += 1

    obs = next_state["blue_observed"]
    link_profile = next_state["world"].get("link_profile", {})
    obs["time"]["received_timestamp"] = next_state["world"]["time"]["true_timestamp"]
    obs["c2_message"]["sequence_number"] = next_state["world"]["command"]["expected_sequence_number"]
    obs["c2_message"]["command"] = next_state["world"]["command"]["last_valid_command"]
    obs["c2_message"]["ack"]["sequence_number"] = obs["c2_message"]["sequence_number"]
    obs["c2_message"]["ack"]["status"] = "ACCEPTED"
    obs["comms"]["latency_ms"] = link_profile.get("latency_ms", 180)
    obs["comms"]["packet_loss"] = link_profile.get("packet_loss", 0.02)
    obs["comms"]["message_queue_depth"] = link_profile.get("message_queue_depth", 3)
    obs["comms"]["packet_interval_jitter_ms"] = link_profile.get("packet_interval_jitter_ms", 18)
    obs["comms"]["packet_size_variance"] = link_profile.get("packet_size_variance", 6)
    obs["comms"]["ack_delay_ms"] = link_profile.get("ack_delay_ms", 210)
    obs["comms"]["heartbeat_gap_ms"] = link_profile.get("heartbeat_gap_ms", 0)
    obs["mission"]["area_priority"] = deepcopy(next_state["world"]["mission"]["area_priority"])
    obs["mission"]["recommended_area"] = "A"
    obs["telemetry"]["battery_percent"] = next_state["world"]["uav"]["battery_percent"]
    obs["telemetry"]["battery_drain_rate"] = next_state["world"]["uav"]["battery_drain_rate"]
    obs["telemetry"]["motor_status"] = next_state["world"]["uav"]["motor_status"]
    sync_external_observe_from_flat(obs)
    refresh_internal_observe_from_truth(next_state)
    return next_state


def _recover_operational_budget(state: dict) -> None:
    previous_cost = sum(
        float(action.get("availability_cost", 0.0))
        for action in state["defense_runtime"].get("active_defenses", [])
    )
    penalty = min(AVAILABILITY_RECOVERY_PER_ROUND, previous_cost * ACTIVE_DEFENSE_RECOVERY_PENALTY)
    availability_recovery = max(0.02, AVAILABILITY_RECOVERY_PER_ROUND - penalty)
    trust_recovery = max(0.01, TRUST_BUDGET_RECOVERY_PER_ROUND - penalty * 0.8)

    mission = state["mission"]
    mission["availability"] = min(1.0, round(mission["availability"] + availability_recovery, 4))
    mission["trust_budget"] = min(1.0, round(mission["trust_budget"] + trust_recovery, 4))
