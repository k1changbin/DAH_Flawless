"""Episode-level runner that groups round-based simulation steps."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Optional

from dah_flawless.config import (
    DEFAULT_EPISODES,
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_SCENARIO,
    DEFAULT_SEED,
    DEFAULT_STEALTH_MODE,
    DEFAULT_STEPS_PER_EPISODE,
)
from dah_flawless.environment.hash_log import GENESIS_HASH, attach_hash, write_jsonl
from dah_flawless.environment.simulator import run_simulation
from dah_flawless.scoring.metrics import summarize_logs


class EpisodeRunner:
    """Run independent 30-step episodes on top of the round-based simulator."""

    def __init__(
        self,
        *,
        seed: int = DEFAULT_SEED,
        episodes: int = DEFAULT_EPISODES,
        steps_per_episode: int = DEFAULT_STEPS_PER_EPISODE,
        scenario: str = DEFAULT_SCENARIO,
        stealth_mode: str = DEFAULT_STEALTH_MODE,
        mutation_profile: str = DEFAULT_MUTATION_PROFILE,
        initial_state: dict | None = None,
    ):
        if episodes < 1:
            raise ValueError("episodes must be >= 1")
        if steps_per_episode < 1:
            raise ValueError("steps_per_episode must be >= 1")

        self.seed = seed
        self.episodes = episodes
        self.steps_per_episode = steps_per_episode
        self.scenario = scenario
        self.stealth_mode = stealth_mode
        self.mutation_profile = mutation_profile
        self.initial_state = deepcopy(initial_state) if initial_state is not None else None

    def run(self) -> tuple[list[dict], dict]:
        all_logs: list[dict] = []
        episode_summaries: list[dict] = []
        prev_hash = GENESIS_HASH
        global_step = 0

        for episode_number in range(1, self.episodes + 1):
            episode_seed = self.seed + episode_number - 1
            episode_initial_state = deepcopy(self.initial_state) if self.initial_state is not None else None
            step_logs, step_summary = run_simulation(
                seed=episode_seed,
                rounds=self.steps_per_episode,
                scenario=self.scenario,
                stealth_mode=self.stealth_mode,
                mutation_profile=self.mutation_profile,
                initial_state=episode_initial_state,
            )

            for step_log in step_logs:
                global_step += 1
                entry_without_hash = _episode_log_body(
                    step_log,
                    episode_number=episode_number,
                    episode_seed=episode_seed,
                    global_step=global_step,
                )
                entry = attach_hash(prev_hash, entry_without_hash)
                prev_hash = entry["this_hash"]
                all_logs.append(entry)

            episode_summary = dict(step_summary)
            episode_summary.update(
                {
                    "episode": episode_number,
                    "episode_seed": episode_seed,
                    "steps_per_episode": self.steps_per_episode,
                    "global_step_start": global_step - len(step_logs) + 1,
                    "global_step_end": global_step,
                }
            )
            episode_summaries.append(episode_summary)

        summary = summarize_logs(all_logs)
        summary.update(
            {
                "runner": "EpisodeRunner",
                "episodes": self.episodes,
                "steps_per_episode": self.steps_per_episode,
                "total_steps": len(all_logs),
                "scenario": self.scenario,
                "stealth_mode": self.stealth_mode,
                "mutation_profile": self.mutation_profile,
                "episode_summaries": episode_summaries,
            }
        )
        return all_logs, summary


def run_episodes(
    *,
    seed: int = DEFAULT_SEED,
    episodes: int = DEFAULT_EPISODES,
    steps_per_episode: int = DEFAULT_STEPS_PER_EPISODE,
    log_path: Optional[Path] = None,
    summary_path: Optional[Path] = None,
    scenario: str = DEFAULT_SCENARIO,
    stealth_mode: str = DEFAULT_STEALTH_MODE,
    mutation_profile: str = DEFAULT_MUTATION_PROFILE,
    initial_state: dict | None = None,
) -> tuple[list[dict], dict]:
    runner = EpisodeRunner(
        seed=seed,
        episodes=episodes,
        steps_per_episode=steps_per_episode,
        scenario=scenario,
        stealth_mode=stealth_mode,
        mutation_profile=mutation_profile,
        initial_state=initial_state,
    )
    logs, summary = runner.run()
    if log_path is not None:
        write_jsonl(log_path, logs)
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return logs, summary


def _episode_log_body(
    step_log: dict,
    *,
    episode_number: int,
    episode_seed: int,
    global_step: int,
) -> dict:
    body = deepcopy(step_log)
    body.pop("prev_hash", None)
    body.pop("this_hash", None)
    body["runner"] = "EpisodeRunner"
    body["episode"] = episode_number
    body["episode_seed"] = episode_seed
    body["episode_step"] = body["round"]
    body["global_step"] = global_step
    return body
