"""Round-based Red/Blue simulation orchestrator."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable, Optional

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
from dah_flawless.blue.observe_policy_gate import evaluate_observe_policy
from dah_flawless.blue.threat_detection import detect_threats
from dah_flawless.blue.zero_trust_gate import evaluate_zero_trust, summarize_zta
from dah_flawless.config import (
    DEFAULT_ROUNDS,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_STEALTH_MODE,
    ROUND_SECONDS,
    SCRIPTED_ATTACKS,
)
from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, write_jsonl
from dah_flawless.environment.log_memory import compress_log_memory, memory_event_from_snapshot, write_memory_snapshot
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.mutation_review import MutationApprovalReviewer, build_mutation_approval_reviewer
from dah_flawless.observation import refresh_internal_observe_from_truth, sync_external_observe_from_flat
from dah_flawless.policy_review import PolicyUpdateReviewer, build_policy_update_reviewer
from dah_flawless.scoring.causal_consistency import assess_causal_consistency
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
    scripted_attacks: tuple[str, ...] = SCRIPTED_ATTACKS,
    memory_compaction_interval: int = 0,
    memory_proxy_size: int = 12,
    memory_path: Path | None = None,
    round_callback: Callable[[dict, list[dict]], None] | None = None,
) -> tuple[list[dict], dict]:
    if memory_compaction_interval < 0:
        raise ValueError("memory_compaction_interval must be >= 0")
    if memory_proxy_size < 1:
        raise ValueError("memory_proxy_size must be >= 1")
    state = deepcopy(initial_state) if initial_state is not None else create_baseline_state(seed, scenario)
    if blue_policy_state is not None:
        apply_blue_policy_state(state, blue_policy_state)
    mark_episode_initial_budget(state, overwrite=True)
    scenario_label = state.get("scenario", scenario)
    history = make_history(state)
    reviewer = policy_update_reviewer or build_policy_update_reviewer()
    mutation_reviewer = mutation_approval_reviewer or build_mutation_approval_reviewer()
    red_agent = RedAgent(
        seed,
        scripted_attacks=scripted_attacks,
        stealth_mode=stealth_mode,
        mutation_profile=mutation_profile,
        policy_state=red_policy_state,
        policy_update_reviewer=reviewer,
    )
    logs: list[dict] = []
    historical_logs = deepcopy(previous_logs or [])
    memory_proxy_logs: list[dict] = []
    active_context_logs: list[dict] = []
    memory_snapshots: list[dict] = []
    if memory_compaction_interval and historical_logs:
        initial_memory = compress_log_memory(
            historical_logs,
            seed=seed,
            compacted_at_step=0,
            proxy_size=memory_proxy_size,
        )
        memory_proxy_logs = deepcopy(initial_memory["proxy_logs"])
        memory_snapshots.append(memory_event_from_snapshot(initial_memory, path=memory_path))
        if memory_path is not None:
            write_memory_snapshot(memory_path, initial_memory)
        historical_logs = []
    threat_history: list[list] = []
    recovery_history: list[dict[str, bool]] = []
    prev_hash = GENESIS_HASH

    for round_number in range(1, rounds + 1):
        state = _advance_normal_state(state, round_number)
        availability_recovery = deepcopy(state.get("defense_runtime", {}).get("availability_recovery", {}))
        redacted_for_red = redact_state(state)
        pre_attack_tag_details = derive_tag_details(redacted_for_red, history, redacted_for_red["capabilities"])
        pre_attack_tags = [detail.tag for detail in pre_attack_tag_details]
        attack, stealth, red_tactic, red_choice_log = red_agent.choose_attack(
            round_number,
            redacted_for_red,
            pre_attack_tags,
            pre_attack_tag_details,
            previous_logs=historical_logs + memory_proxy_logs + active_context_logs,
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
        zta_decisions, zta_log = evaluate_zero_trust(
            redacted_for_blue["blue_observed"],
            history,
            redacted_for_blue["capabilities"],
            redacted_for_blue["defense_runtime"].get("domain_trust", {}),
            redacted_for_blue["mission"],
            threats,
        )
        zta_policy = summarize_zta([zta_decisions], attack.target_domain)
        observe_policy_gate, observe_policy_log = evaluate_observe_policy(
            redacted_for_blue,
            history,
            attacked_state["capabilities"],
        )
        attacked_state.setdefault("defense_runtime", {})["observe_policy_gate"] = observe_policy_gate
        pre_defense_state.setdefault("defense_runtime", {})["observe_policy_gate"] = deepcopy(observe_policy_gate)
        risks, risk_log = estimate_mission_risk(redacted_for_blue, threats, zta_decisions)
        actions, defense_log = plan_defense(
            threats,
            risks,
            attacked_state["mission"],
            attacked_state["defense_runtime"],
            zta_decisions,
        )
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
            zta_decisions=zta_decisions,
        )
        causal_consistency, causal_log = assess_causal_consistency(
            attack=attack,
            red_goal=red_goal,
            red_tactic=red_tactic,
            mutation_log=mutation_log,
            pre_attack_tags=pre_attack_tags,
            situation_tags=situation_tags,
            threats=threats,
            score=score,
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
            "scenario_profile": deepcopy(state.get("scenario_profile", {})),
            "mutation_profile": mutation_profile,
            "update_mode": {
                "red_update_enabled": red_update_enabled,
                "blue_update_enabled": blue_update_enabled,
            },
            "truth_model": "scorer_truth",
            "truth_storage_key": 'state["world"]',
            "raw_world_source_hash": state["world"].get("raw_world_hash"),
            "raw_world_feature_scores": deepcopy(state["world"].get("raw_world_feature_scores", {})),
            "availability_recovery": availability_recovery,
            "red_situation_tags": pre_attack_tags,
            "red_situation_tag_details": [detail.to_dict() for detail in pre_attack_tag_details],
            "situation_tags": situation_tags,
            "attack": attack.to_dict(),
            "stealth": stealth,
            "red_goal": red_goal,
            "red_tactic": red_tactic,
            "threats": [threat.to_dict() for threat in threats],
            "zta_decisions": [item.to_dict() for item in zta_decisions],
            "zta_policy": zta_policy,
            "mission_risks": [risk.to_dict() for risk in risks],
            "observe_policy_gate": deepcopy(observe_policy_gate),
            "defense_actions": defended_state["defense_runtime"]["active_defenses"],
            "score": score.to_dict(),
            "causal_consistency": causal_consistency,
            "incident_report": report,
            "red_policy_state": red_agent.export_policy_state(),
            "blue_policy_state": export_blue_policy_state(defended_state),
            "feedback": {
                "red_policy_updated": red_update_enabled,
                "blue_policy_updated": blue_update_enabled,
                "winner": score.winner,
                "winner_side": score.winner_side,
                "winner_detail": score.winner_detail,
                "outcome_reason": score.outcome_reason,
                "target_domain": attack.target_domain,
                "goal_id": score.goal_id,
                "attack_success": score.attack_success,
                "goal_success": score.goal_success,
                "goal_reward": score.goal_reward,
                "attempted_effect_success": score.attempted_effect_success,
                "pre_defense_goal_success": score.pre_defense_goal_success,
                "post_defense_effective_breach": score.post_defense_effective_breach,
                "blue_recovered": score.blue_recovered,
                "mission_impact_score": score.evidence.get("mission_impact", {}).get("mission_impact_score"),
                "policy_decision_correctness": zta_policy["policy_decision_correctness"],
                "causal_consistency_score": causal_consistency["consistency_score"],
                "causal_consistency_status": causal_consistency["status"],
                "detection_success": score.detection_success,
                "recovery_success": score.recovery_success,
            },
            "decision_log": [
                red_choice_log,
                mutation_log,
                threat_log,
                blue_detection_policy_log,
                zta_log,
                observe_policy_log,
                risk_log,
                defense_log,
                causal_log,
                report_log,
                blue_update_log,
                red_update_log,
            ],
            "red_input_redacted": "world" not in redacted_for_red,
            "blue_input_redacted": "world" not in redacted_for_blue,
        }
        should_compact_memory = (
            memory_compaction_interval > 0
            and len(active_context_logs) + 1 >= memory_compaction_interval
        )
        if should_compact_memory:
            memory_source_logs = [*memory_proxy_logs, *active_context_logs, entry_without_hash]
            memory_snapshot = compress_log_memory(
                memory_source_logs,
                seed=seed,
                compacted_at_step=round_number,
                proxy_size=memory_proxy_size,
            )
            memory_event = memory_event_from_snapshot(memory_snapshot, path=memory_path)
            entry_without_hash["log_memory_event"] = memory_event
        entry = attach_hash(prev_hash, entry_without_hash)
        logs.append(entry)
        active_context_logs.append(entry)
        if should_compact_memory:
            memory_proxy_logs = deepcopy(memory_snapshot["proxy_logs"])
            active_context_logs = []
            memory_snapshots.append(memory_event)
            if memory_path is not None:
                write_memory_snapshot(memory_path, memory_snapshot)
        if round_callback is not None:
            round_callback(entry, logs)
        prev_hash = entry["this_hash"]
        threat_history.append(threats)
        recovery_history.append(
            {attack.target_domain: bool(score.evidence.get("current_recovery_success", score.recovery_success))}
        )

        state = defended_state
        history = make_history(state)

    summary = summarize_logs(logs)
    summary["scenario"] = scenario_label
    summary["scenario_profile"] = deepcopy(state.get("scenario_profile", {}))
    summary["stealth_mode"] = stealth_mode
    summary["mutation_profile"] = mutation_profile
    summary["update_mode"] = {
        "red_update_enabled": red_update_enabled,
        "blue_update_enabled": blue_update_enabled,
    }
    summary["red_policy_state"] = red_agent.export_policy_state()
    summary["blue_policy_state"] = export_blue_policy_state(state)
    if memory_compaction_interval:
        summary["log_memory"] = {
            "enabled": True,
            "compaction_interval": memory_compaction_interval,
            "proxy_size": memory_proxy_size,
            "compaction_count": len(memory_snapshots),
            "proxy_context_log_count": len(memory_proxy_logs),
            "active_context_log_count": len(active_context_logs),
            "memory_path": str(memory_path) if memory_path is not None else None,
            "snapshots": memory_snapshots,
        }
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
    _reset_round_operational_budget(next_state, round_number)
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


def mark_episode_initial_budget(state: dict, *, overwrite: bool = False) -> dict:
    """Record the per-round combat budget baseline for this simulation run."""

    runtime = state.setdefault("defense_runtime", {})
    if overwrite or "episode_initial_budget" not in runtime:
        mission = state["mission"]
        runtime["episode_initial_budget"] = {
            "availability": round(float(mission.get("availability", 1.0)), 4),
            "trust_budget": round(float(mission.get("trust_budget", 1.0)), 4),
        }
    return state


def _reset_round_operational_budget(state: dict, round_number: int) -> None:
    runtime = state.setdefault("defense_runtime", {})
    mission = state["mission"]
    mark_episode_initial_budget(state)

    initial_budget = runtime["episode_initial_budget"]
    target_availability = round(float(initial_budget.get("availability", 1.0)), 4)
    target_trust = round(float(initial_budget.get("trust_budget", 1.0)), 4)
    availability_before = round(float(mission.get("availability", target_availability)), 4)
    trust_before = round(float(mission.get("trust_budget", target_trust)), 4)
    active_defenses = runtime.get("active_defenses", [])
    pending_defenses = runtime.get("pending_defenses", [])
    previous_cost = sum(float(action.get("availability_cost", 0.0)) for action in active_defenses)

    mission["availability"] = target_availability
    mission["trust_budget"] = target_trust
    runtime["active_defenses"] = []
    runtime["pending_defenses"] = []
    runtime.pop("combat_attrition", None)
    runtime.pop("combat_budget", None)
    runtime.pop("red_combat_pressure", None)
    runtime["availability_recovery"] = {
        "algorithm": "round_episode_budget_reset_v1",
        "round": round_number,
        "scope": "round_episode",
        "reset_scope": "availability_fight_only_inside_one_episode",
        "previous_active_defense_cost": round(previous_cost, 4),
        "cleared_active_defense_count": len(active_defenses),
        "cleared_pending_defense_count": len(pending_defenses),
        "maintenance_cycle": False,
        "availability_before": availability_before,
        "availability_after": target_availability,
        "availability_reset_target": target_availability,
        "availability_reset_delta": round(target_availability - availability_before, 4),
        "availability_recovery_planned": 0.0,
        "availability_recovery_applied": 0.0,
        "trust_before": trust_before,
        "trust_after": target_trust,
        "trust_reset_target": target_trust,
        "trust_reset_delta": round(target_trust - trust_before, 4),
        "trust_recovery_planned": 0.0,
        "trust_recovery_applied": 0.0,
    }
