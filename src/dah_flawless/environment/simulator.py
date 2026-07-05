"""Round-based Red/Blue simulation orchestrator."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Optional

from dah_flawless.attacks.mutations import apply_attack
from dah_flawless.attacks.red_agent import RedAgent
from dah_flawless.blue.defense_planner import apply_defense_actions, plan_defense
from dah_flawless.blue.incident_report import write_incident_report
from dah_flawless.blue.mission_monitor import estimate_mission_risk
from dah_flawless.blue.tagger import derive_tags
from dah_flawless.blue.threat_detection import detect_threats
from dah_flawless.config import (
    ACTIVE_DEFENSE_RECOVERY_PENALTY,
    AVAILABILITY_RECOVERY_PER_ROUND,
    DEFAULT_ROUNDS,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_STEALTH_MODE,
    ROUND_SECONDS,
    TRUST_BUDGET_RECOVERY_PER_ROUND,
)
from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, write_jsonl
from dah_flawless.environment.redaction import redact_state
from dah_flawless.environment.state_factory import create_baseline_state, make_history
from dah_flawless.scoring.metrics import summarize_logs
from dah_flawless.scoring.scorer import score_round


def run_simulation(
    seed: int = DEFAULT_SEED,
    rounds: int = DEFAULT_ROUNDS,
    log_path: Optional[Path] = None,
    summary_path: Optional[Path] = None,
    scenario: str = DEFAULT_SCENARIO,
    stealth_mode: str = DEFAULT_STEALTH_MODE,
) -> tuple[list[dict], dict]:
    state = create_baseline_state(seed, scenario)
    history = make_history(state)
    red_agent = RedAgent(seed, stealth_mode=stealth_mode)
    logs: list[dict] = []
    prev_hash = GENESIS_HASH

    for round_number in range(1, rounds + 1):
        state = _advance_normal_state(state, round_number)
        redacted_for_red = redact_state(state)
        pre_attack_tags = derive_tags(redacted_for_red, history, redacted_for_red["capabilities"])
        attack, stealth, red_tactic, red_choice_log = red_agent.choose_attack(
            round_number, redacted_for_red, pre_attack_tags
        )

        attacked_state, mutation_log = apply_attack(state, attack, stealth=stealth, tactic=red_tactic)
        pre_defense_state = deepcopy(attacked_state)

        redacted_for_blue = redact_state(attacked_state)
        situation_tags, threats, threat_log = detect_threats(
            redacted_for_blue, history, attacked_state["capabilities"]
        )
        risks, risk_log = estimate_mission_risk(redacted_for_blue, threats)
        actions, defense_log = plan_defense(threats, risks, attacked_state["mission"], attacked_state["defense_runtime"])
        defended_state = apply_defense_actions(attacked_state, actions, history, threats, attacked_state["capabilities"])
        score = score_round(pre_defense_state, defended_state, attack, threats, actions)
        report, report_log = write_incident_report(threats, risks, actions, score)
        red_update_log = red_agent.update_weight(attack.name, score.detection_success)
        red_policy_state = red_agent.snapshot_policy()
        blue_policy_state = defense_log["after"].get("policy_state", {})

        entry_without_hash = {
            "round": round_number,
            "seed": seed,
            "scenario": scenario,
            "situation_tags": situation_tags,
            "attack": attack.to_dict(),
            "stealth": stealth,
            "red_tactic": red_tactic,
            "threats": [threat.to_dict() for threat in threats],
            "mission_risks": [risk.to_dict() for risk in risks],
            "defense_actions": defended_state["defense_runtime"]["active_defenses"],
            "score": score.to_dict(),
            "feedback": {
                "red": {
                    "attack_success": score.attack_success,
                    "detection_success": score.detection_success,
                    "winner": score.winner,
                },
                "blue": {
                    "recovery_success": score.recovery_success,
                    "availability": score.availability,
                    "false_positive": score.false_positive,
                    "winner": score.winner,
                },
            },
            "red_policy_state": red_policy_state,
            "blue_policy_state": blue_policy_state,
            "incident_report": report,
            "decision_log": [
                red_choice_log,
                mutation_log,
                threat_log,
                risk_log,
                defense_log,
                report_log,
                red_update_log,
            ],
            "red_input_redacted": "world" not in redacted_for_red,
            "blue_input_redacted": "world" not in redacted_for_blue,
        }
        entry = attach_hash(prev_hash, entry_without_hash)
        logs.append(entry)
        prev_hash = entry["this_hash"]

        state = defended_state
        history = make_history(state)

    summary = summarize_logs(logs)
    summary["scenario"] = scenario
    summary["stealth_mode"] = stealth_mode
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

    world = next_state["world"]
    obs = next_state["blue_observed"]
    obs["time"]["received_timestamp"] = world["time"]["true_timestamp"]
    obs["c2_message"]["sequence_number"] = world["command"]["expected_sequence_number"]
    obs["c2_message"]["command"] = world["command"]["last_valid_command"]
    obs["comms"]["latency_ms"] = 180
    obs["comms"]["packet_loss"] = 0.02
    obs["comms"]["message_queue_depth"] = 3
    obs["mission"]["area_priority"] = deepcopy(world["mission"]["area_priority"])
    obs["mission"]["recommended_area"] = world["mission"]["current_area"]
    obs["telemetry"]["battery_percent"] = world["uav"]["battery_percent"]
    obs["telemetry"]["battery_drain_rate"] = world["uav"]["battery_drain_rate"]
    obs["telemetry"]["motor_status"] = world["uav"]["motor_status"]
    obs["telemetry"]["altitude_m"] = world["uav"]["position"]["altitude_m"]
    obs["telemetry"]["speed_mps"] = world["uav"]["speed_mps"]
    obs["telemetry"]["heading_deg"] = world["uav"]["heading_deg"]
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
