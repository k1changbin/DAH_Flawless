"""Alternating Red/Blue training scheduler for episode-level runs."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dah_flawless.attacks.red_agent import RedAgent
from dah_flawless.blue.feedback_learner import default_blue_policy_state
from dah_flawless.config import (
    DEFAULT_BLUE_UPDATE_EPISODES,
    DEFAULT_EVAL_EPISODES,
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_RED_UPDATE_EPISODES,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_STEALTH_MODE,
    DEFAULT_STEPS_PER_EPISODE,
)
from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, write_jsonl
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.scoring.metrics import summarize_logs


@dataclass(frozen=True)
class TrainingBlock:
    name: str
    episodes: int
    red_update_enabled: bool
    blue_update_enabled: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "episodes": self.episodes,
            "red_update_enabled": self.red_update_enabled,
            "blue_update_enabled": self.blue_update_enabled,
        }


class TrainingScheduler:
    """Run alternating update blocks while carrying policy state across episodes."""

    def __init__(
        self,
        *,
        seed: int = DEFAULT_SEED,
        blue_update_episodes: int = DEFAULT_BLUE_UPDATE_EPISODES,
        red_update_episodes: int = DEFAULT_RED_UPDATE_EPISODES,
        eval_episodes: int = DEFAULT_EVAL_EPISODES,
        steps_per_episode: int = DEFAULT_STEPS_PER_EPISODE,
        scenario: str = DEFAULT_SCENARIO,
        stealth_mode: str = DEFAULT_STEALTH_MODE,
        mutation_profile: str = DEFAULT_MUTATION_PROFILE,
        initial_state: dict | None = None,
        red_policy_state: dict | None = None,
        blue_policy_state: dict | None = None,
    ):
        _validate_non_negative("blue_update_episodes", blue_update_episodes)
        _validate_non_negative("red_update_episodes", red_update_episodes)
        _validate_non_negative("eval_episodes", eval_episodes)
        if blue_update_episodes + red_update_episodes + eval_episodes < 1:
            raise ValueError("training schedule must contain at least one episode")
        if steps_per_episode < 1:
            raise ValueError("steps_per_episode must be >= 1")

        self.seed = seed
        self.steps_per_episode = steps_per_episode
        self.scenario = scenario
        self.stealth_mode = stealth_mode
        self.mutation_profile = mutation_profile
        self.initial_state = deepcopy(initial_state) if initial_state is not None else None
        self.red_policy_state = (
            deepcopy(red_policy_state)
            if red_policy_state is not None
            else _default_red_policy_state(seed, stealth_mode, mutation_profile)
        )
        self.blue_policy_state = (
            deepcopy(blue_policy_state) if blue_policy_state is not None else _default_blue_policy_state()
        )
        self.blocks = [
            TrainingBlock("BLUE_UPDATE", blue_update_episodes, red_update_enabled=False, blue_update_enabled=True),
            TrainingBlock("RED_UPDATE", red_update_episodes, red_update_enabled=True, blue_update_enabled=False),
            TrainingBlock("FIXED_EVAL", eval_episodes, red_update_enabled=False, blue_update_enabled=False),
        ]

    def run(self) -> tuple[list[dict], dict]:
        all_logs: list[dict] = []
        block_summaries: list[dict] = []
        prev_hash = GENESIS_HASH
        global_step = 0
        episode_number = 0
        red_policy_state = deepcopy(self.red_policy_state)
        blue_policy_state = deepcopy(self.blue_policy_state)

        for block_index, block in enumerate(self.blocks, start=1):
            if block.episodes == 0:
                continue

            block_logs: list[dict] = []
            episode_summaries: list[dict] = []
            block_red_policy_start = deepcopy(red_policy_state)
            block_blue_policy_start = deepcopy(blue_policy_state)

            for episode_in_block in range(1, block.episodes + 1):
                episode_number += 1
                episode_seed = self.seed + episode_number - 1
                episode_initial_state = deepcopy(self.initial_state) if self.initial_state is not None else None
                step_logs, step_summary = run_simulation(
                    seed=episode_seed,
                    rounds=self.steps_per_episode,
                    scenario=self.scenario,
                    stealth_mode=self.stealth_mode,
                    mutation_profile=self.mutation_profile,
                    initial_state=episode_initial_state,
                    red_update_enabled=block.red_update_enabled,
                    blue_update_enabled=block.blue_update_enabled,
                    red_policy_state=red_policy_state,
                    blue_policy_state=blue_policy_state,
                )
                red_policy_state = deepcopy(step_summary["red_policy_state"])
                blue_policy_state = deepcopy(step_summary["blue_policy_state"])

                for step_log in step_logs:
                    global_step += 1
                    body = _training_log_body(
                        step_log,
                        block=block,
                        block_index=block_index,
                        episode_number=episode_number,
                        episode_in_block=episode_in_block,
                        episode_seed=episode_seed,
                        global_step=global_step,
                    )
                    entry = attach_hash(prev_hash, body)
                    prev_hash = entry["this_hash"]
                    all_logs.append(entry)
                    block_logs.append(entry)

                episode_summary = dict(step_summary)
                episode_summary.update(
                    {
                        "runner": "TrainingScheduler",
                        "block": block.name,
                        "block_index": block_index,
                        "episode": episode_number,
                        "episode_in_block": episode_in_block,
                        "episode_seed": episode_seed,
                        "steps_per_episode": self.steps_per_episode,
                        "global_step_start": global_step - len(step_logs) + 1,
                        "global_step_end": global_step,
                    }
                )
                episode_summaries.append(episode_summary)

            block_summary = summarize_logs(block_logs)
            block_summary.update(
                {
                    "block": block.name,
                    "block_index": block_index,
                    "episodes": block.episodes,
                    "steps_per_episode": self.steps_per_episode,
                    "red_update_enabled": block.red_update_enabled,
                    "blue_update_enabled": block.blue_update_enabled,
                    "red_policy_start": block_red_policy_start,
                    "red_policy_end": deepcopy(red_policy_state),
                    "blue_policy_start": block_blue_policy_start,
                    "blue_policy_end": deepcopy(blue_policy_state),
                    "episode_summaries": episode_summaries,
                }
            )
            block_summaries.append(block_summary)

        summary = summarize_logs(all_logs)
        summary.update(
            {
                "runner": "TrainingScheduler",
                "episodes": episode_number,
                "steps_per_episode": self.steps_per_episode,
                "total_steps": len(all_logs),
                "scenario": self.scenario,
                "stealth_mode": self.stealth_mode,
                "mutation_profile": self.mutation_profile,
                "schedule": [block.to_dict() for block in self.blocks],
                "block_summaries": block_summaries,
                "final_red_policy_state": red_policy_state,
                "final_blue_policy_state": blue_policy_state,
            }
        )
        return all_logs, summary


def run_training_schedule(
    *,
    seed: int = DEFAULT_SEED,
    blue_update_episodes: int = DEFAULT_BLUE_UPDATE_EPISODES,
    red_update_episodes: int = DEFAULT_RED_UPDATE_EPISODES,
    eval_episodes: int = DEFAULT_EVAL_EPISODES,
    steps_per_episode: int = DEFAULT_STEPS_PER_EPISODE,
    log_path: Optional[Path] = None,
    summary_path: Optional[Path] = None,
    scenario: str = DEFAULT_SCENARIO,
    stealth_mode: str = DEFAULT_STEALTH_MODE,
    mutation_profile: str = DEFAULT_MUTATION_PROFILE,
    initial_state: dict | None = None,
) -> tuple[list[dict], dict]:
    scheduler = TrainingScheduler(
        seed=seed,
        blue_update_episodes=blue_update_episodes,
        red_update_episodes=red_update_episodes,
        eval_episodes=eval_episodes,
        steps_per_episode=steps_per_episode,
        scenario=scenario,
        stealth_mode=stealth_mode,
        mutation_profile=mutation_profile,
        initial_state=initial_state,
    )
    logs, summary = scheduler.run()
    if log_path is not None:
        write_jsonl(log_path, logs)
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return logs, summary


def _training_log_body(
    step_log: dict,
    *,
    block: TrainingBlock,
    block_index: int,
    episode_number: int,
    episode_in_block: int,
    episode_seed: int,
    global_step: int,
) -> dict:
    body = deepcopy(step_log)
    body.pop("prev_hash", None)
    body.pop("this_hash", None)
    body["runner"] = "TrainingScheduler"
    body["block"] = block.name
    body["block_index"] = block_index
    body["episode"] = episode_number
    body["episode_in_block"] = episode_in_block
    body["episode_seed"] = episode_seed
    body["episode_step"] = body["round"]
    body["global_step"] = global_step
    body["update_mode"] = {
        "red_update_enabled": block.red_update_enabled,
        "blue_update_enabled": block.blue_update_enabled,
    }
    return body


def _default_red_policy_state(seed: int, stealth_mode: str, mutation_profile: str) -> dict:
    return RedAgent(seed, stealth_mode=stealth_mode, mutation_profile=mutation_profile).export_policy_state()


def _default_blue_policy_state() -> dict:
    return default_blue_policy_state()


def _validate_non_negative(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
