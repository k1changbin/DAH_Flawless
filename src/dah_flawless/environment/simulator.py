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
from dah_flawless.config import DEFAULT_ROUNDS, DEFAULT_SEED, ROUND_SECONDS
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
) -> tuple[list[dict], dict]:
    state = create_baseline_state(seed)
    history = make_history(state)
    red_agent = RedAgent(seed)
    logs: list[dict] = []
    prev_hash = GENESIS_HASH

    for round_number in range(1, rounds + 1):
        state = _advance_normal_state(state, round_number)
        redacted_for_red = redact_state(state)
        pre_attack_tags = derive_tags(redacted_for_red, history)
        attack, red_choice_log = red_agent.choose_attack(round_number, redacted_for_red, pre_attack_tags)

        attacked_state, mutation_log = apply_attack(state, attack)
        pre_defense_state = deepcopy(attacked_state)

        redacted_for_blue = redact_state(attacked_state)
        situation_tags, threats, threat_log = detect_threats(redacted_for_blue, history)
        risks, risk_log = estimate_mission_risk(redacted_for_blue, threats)
        actions, defense_log = plan_defense(threats, risks, attacked_state["mission"])
        defended_state = apply_defense_actions(attacked_state, actions, history)
        score = score_round(pre_defense_state, defended_state, attack, threats, actions)
        report, report_log = write_incident_report(threats, risks, actions, score)
        red_update_log = red_agent.update_weight(attack.name, score.detection_success)

        entry_without_hash = {
            "round": round_number,
            "seed": seed,
            "situation_tags": situation_tags,
            "attack": attack.to_dict(),
            "threats": [threat.to_dict() for threat in threats],
            "mission_risks": [risk.to_dict() for risk in risks],
            "defense_actions": defended_state["defense_runtime"]["active_defenses"],
            "score": score.to_dict(),
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
    next_state["world"]["time"]["round"] = round_number
    next_state["world"]["time"]["true_timestamp"] += ROUND_SECONDS
    next_state["world"]["command"]["expected_sequence_number"] += 1

    obs = next_state["blue_observed"]
    obs["time"]["received_timestamp"] = next_state["world"]["time"]["true_timestamp"]
    obs["c2_message"]["sequence_number"] = next_state["world"]["command"]["expected_sequence_number"]
    obs["c2_message"]["command"] = next_state["world"]["command"]["last_valid_command"]
    obs["comms"]["latency_ms"] = 180
    obs["comms"]["packet_loss"] = 0.02
    obs["comms"]["message_queue_depth"] = 3
    obs["mission"]["area_priority"] = deepcopy(next_state["world"]["mission"]["area_priority"])
    obs["mission"]["recommended_area"] = "A"
    obs["telemetry"]["battery_percent"] = next_state["world"]["uav"]["battery_percent"]
    obs["telemetry"]["motor_status"] = next_state["world"]["uav"]["motor_status"]
    return next_state
