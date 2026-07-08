from __future__ import annotations

import html
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dah_flawless.config import (  # noqa: E402
    DEFAULT_MUTATION_PROFILE,
    DEFAULT_ROUNDS,
    DEFAULT_SEED,
    MUTATION_PROFILES,
    SCENARIOS,
    STEALTH_MODES,
)
from dah_flawless.environment.hash_log import verify_hash_chain  # noqa: E402
from dah_flawless.environment.round_combat_runner import (  # noqa: E402
    DEFAULT_MAX_COMBAT_STEPS,
    DEFAULT_MIN_COMBAT_STEPS,
    run_combat_rounds,
)
from dah_flawless.environment.simulator import run_simulation  # noqa: E402
from dah_flawless.scoring.metrics import summarize_logs  # noqa: E402
from dah_flawless.world.state_adapter import build_state_from_raw_world  # noqa: E402

DEFAULT_LOG_PATH = ROOT / "data" / "logs" / "round_logs.jsonl"
DEFAULT_SUMMARY_PATH = ROOT / "data" / "logs" / "summary.json"
DEFAULT_MEMORY_PATH = ROOT / "data" / "logs" / "rolling_memory.json"
RUNNER_MODES = ("classic_rounds", "dynamic_combat")


@dataclass(frozen=True)
class RunRequest:
    seed: int
    rounds: int
    runner_mode: str
    scenario: str
    stealth_mode: str
    mutation_profile: str
    log_path: Path
    raw_world_text: str
    memory_enabled: bool
    memory_compaction_interval: int
    memory_proxy_size: int
    memory_path: Path
    max_steps: int
    min_steps: int
    live_playback: bool
    playback_delay_ms: int


def main() -> None:
    st.set_page_config(
        page_title="DAH // FLAWLESS",
        page_icon="DAH",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_style()

    log_path, run_request = _sidebar_controls()
    if run_request is not None:
        logs, summary = _run_simulation_live(run_request)
        hash_valid = verify_hash_chain(logs) if logs else False
    else:
        logs = _load_logs(log_path)
        summary = summarize_logs(logs) if logs else {}
        hash_valid = verify_hash_chain(logs) if logs else False

    _render_command_bar(logs, summary, hash_valid, log_path)

    if not logs:
        _render_empty_state(log_path)
        return

    selected_round = _selected_round(logs)
    _render_metric_tiles(summary, hash_valid, logs)
    _render_ops_brief(logs, summary, hash_valid, selected_round)

    overview_tab, timeline_tab, diff_tab, chart_tab, decision_tab = st.tabs(
        ["01 OVERVIEW", "02 TIMELINE", "03 SCORER DIFF", "04 CHARTS", "05 DECISIONS"]
    )

    with overview_tab:
        _render_overview(logs, summary)
    with timeline_tab:
        _render_timeline(logs, selected_round)
    with diff_tab:
        _render_diff(logs)
    with chart_tab:
        _render_charts(logs)
    with decision_tab:
        _render_decisions(logs)


# --------------------------------------------------------------------------- #
#  Controls
# --------------------------------------------------------------------------- #
def _sidebar_controls() -> tuple[Path, RunRequest | None]:
    st.sidebar.markdown(
        """
        <div class="side-brand">
          <div class="side-kicker"><span></span> MISSION CONTROL</div>
          <div class="side-title">DAH FLAWLESS</div>
          <div class="side-sub">Red x Blue adversarial simulation</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar.form("mission_controls"):
        st.markdown('<div class="form-label">RUN PARAMETERS</div>', unsafe_allow_html=True)
        seed = st.number_input("Seed", min_value=0, value=DEFAULT_SEED, step=1)
        rounds = st.number_input("Rounds", min_value=1, max_value=24, value=DEFAULT_ROUNDS, step=1)
        runner_mode = st.selectbox(
            "Runner",
            RUNNER_MODES,
            index=0,
            format_func=lambda value: "Classic rounds" if value == "classic_rounds" else "Dynamic combat",
            help="Dynamic combat stores per-round Red/Blue decision steps for node-level inspection.",
        )
        scenario = st.selectbox(
            "Scenario",
            SCENARIOS,
            index=0,
            help="degraded_start begins with lower availability and degraded capability.",
        )
        red_stealth = st.selectbox(
            "Red stealth",
            STEALTH_MODES,
            index=0,
            help="on/adaptive lets Red reduce observable mutations after detection.",
        )
        mutation_profile = st.selectbox(
            "Mutation profile",
            MUTATION_PROFILES,
            index=MUTATION_PROFILES.index(DEFAULT_MUTATION_PROFILE),
        )
        log_path_text = st.text_input("Log path", str(DEFAULT_LOG_PATH.relative_to(ROOT)))
        raw_world_text = st.text_input(
            "Raw world sample",
            "",
            help="Optional JSON/JSONL sample from scripts/run_world_generator.py.",
        )
        max_steps = st.number_input(
            "Dynamic max steps",
            min_value=DEFAULT_MIN_COMBAT_STEPS,
            max_value=DEFAULT_MAX_COMBAT_STEPS,
            value=30,
            step=1,
            help="Only used by Dynamic combat.",
        )
        min_steps = st.number_input(
            "Dynamic min steps",
            min_value=1,
            max_value=DEFAULT_MAX_COMBAT_STEPS,
            value=DEFAULT_MIN_COMBAT_STEPS,
            step=1,
            help="Only used by Dynamic combat.",
        )
        memory_enabled = st.checkbox(
            "Rolling memory",
            value=False,
            help="Classic runner only. Compacts prior rounds into a proxy planning context.",
        )
        memory_compaction_interval = 0
        memory_proxy_size = 12
        memory_path_text = str(DEFAULT_MEMORY_PATH.relative_to(ROOT))
        if memory_enabled:
            memory_compaction_interval = st.number_input(
                "Memory interval",
                min_value=1,
                max_value=100,
                value=20,
                step=1,
            )
            memory_proxy_size = st.number_input(
                "Memory proxy size",
                min_value=1,
                max_value=50,
                value=12,
                step=1,
            )
            memory_path_text = st.text_input("Memory path", str(DEFAULT_MEMORY_PATH.relative_to(ROOT)))
        live_playback = st.checkbox("Live playback", value=True)
        playback_delay_ms = st.slider(
            "Frame delay (ms)",
            min_value=0,
            max_value=500,
            value=120,
            step=20,
            help="Adds a small UI delay so round-by-round simulation is visible.",
        )
        submitted = st.form_submit_button("EXECUTE SIMULATION", type="primary", width="stretch")

    log_path = (ROOT / log_path_text).resolve()
    memory_path = (ROOT / memory_path_text).resolve()
    run_request = None
    if submitted:
        run_request = RunRequest(
            seed=int(seed),
            rounds=int(rounds),
            runner_mode=str(runner_mode),
            scenario=str(scenario),
            stealth_mode=str(red_stealth),
            mutation_profile=str(mutation_profile),
            log_path=log_path,
            raw_world_text=raw_world_text,
            memory_enabled=bool(memory_enabled),
            memory_compaction_interval=int(memory_compaction_interval),
            memory_proxy_size=int(memory_proxy_size),
            memory_path=memory_path,
            max_steps=int(max_steps),
            min_steps=int(min_steps),
            live_playback=bool(live_playback),
            playback_delay_ms=int(playback_delay_ms),
        )

    st.sidebar.markdown(
        """
        <div class="side-foot">
          <span>SEED LOCKED</span>
          <span>HASH CHAINED</span>
          <span>REPRODUCIBLE</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return log_path, run_request


@st.cache_data(show_spinner=False)
def _read_text(path_text: str, modified_ns: int) -> str:
    del modified_ns
    return Path(path_text).read_text(encoding="utf-8")


def _load_logs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = _read_text(str(path), path.stat().st_mtime_ns)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _resolve_input_path(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def _read_raw_world_sample(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if not first_line:
        raise ValueError(f"empty raw-world sample file: {path}")
    return json.loads(first_line)


def _selected_round(logs: list[dict[str, Any]]) -> int:
    fallback = _round_number(logs[-1])
    raw_round: Any = None
    try:
        raw_round = st.query_params.get("round")
    except AttributeError:
        raw_round = None
    if isinstance(raw_round, list):
        raw_round = raw_round[0] if raw_round else None
    try:
        selected = int(raw_round) if raw_round is not None else fallback
    except (TypeError, ValueError):
        selected = fallback
    valid_rounds = {_round_number(entry) for entry in logs}
    return selected if selected in valid_rounds else fallback


def _entry_for_round(logs: list[dict[str, Any]], selected_round: int | None) -> dict[str, Any]:
    if selected_round is not None:
        for entry in logs:
            if _round_number(entry) == selected_round:
                return entry
    return logs[-1]


def _round_number(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("round", 0))
    except (TypeError, ValueError):
        return 0


# --------------------------------------------------------------------------- #
#  Live run
# --------------------------------------------------------------------------- #
def _run_simulation_live(request: RunRequest) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    initial_state = None
    if request.raw_world_text.strip():
        raw_world_path = _resolve_input_path(request.raw_world_text)
        if not raw_world_path.exists():
            st.error(f"Raw world sample not found: {raw_world_path}")
            logs = _load_logs(request.log_path)
            return logs, summarize_logs(logs) if logs else {}
        initial_state = build_state_from_raw_world(_read_raw_world_sample(raw_world_path), seed=request.seed)

    _section("Live simulation", "round-by-round execution stream")
    progress_slot = st.empty()
    map_slot = st.empty()
    table_slot = st.empty()
    signal_slot = st.empty()
    progress_slot.progress(0, text="Preparing adversarial episode...")

    def on_round(entry: dict, partial_logs: list[dict]) -> None:
        progress = min(1.0, entry["round"] / max(1, request.rounds))
        progress_slot.progress(
            progress,
            text=(
                f'Round {entry["round"]:02d}/{request.rounds:02d} | '
                f'{entry["attack"]["name"]} | winner {entry["score"]["winner"]}'
            ),
        )
        hash_ok = verify_hash_chain(partial_logs)
        map_slot.markdown(
            _map_panel_html(partial_logs, hash_ok, title="LIVE THEATER TRACE", selected_round=entry["round"]),
            unsafe_allow_html=True,
        )
        table_slot.dataframe(_scoreboard_rows(partial_logs), width="stretch", hide_index=True)
        signal_slot.markdown(_live_signal_html(entry, partial_logs), unsafe_allow_html=True)
        if request.live_playback and request.playback_delay_ms > 0:
            time.sleep(request.playback_delay_ms / 1000)

    if request.runner_mode == "dynamic_combat":
        if request.raw_world_text.strip():
            st.warning("Dynamic combat currently uses scenario presets; raw-world samples run through Classic rounds.")
        min_steps = min(request.min_steps, request.max_steps)
        logs, run_summary = run_combat_rounds(
            seed=request.seed,
            rounds=request.rounds,
            max_steps=request.max_steps,
            min_steps=min_steps,
            scenario=request.scenario,
            stealth_mode=request.stealth_mode,
            mutation_profile=request.mutation_profile,
            log_path=request.log_path,
            summary_path=DEFAULT_SUMMARY_PATH,
        )
        progress_slot.progress(1.0, text=f"Dynamic combat complete | {len(logs)} rounds committed")
        if logs:
            hash_ok = verify_hash_chain(logs)
            map_slot.markdown(
                _map_panel_html(logs, hash_ok, title="DYNAMIC COMBAT TRACE"),
                unsafe_allow_html=True,
            )
            table_slot.dataframe(_scoreboard_rows(logs), width="stretch", hide_index=True)
            signal_slot.markdown(_live_signal_html(logs[-1], logs), unsafe_allow_html=True)
    else:
        logs, run_summary = run_simulation(
            seed=request.seed,
            rounds=request.rounds,
            log_path=request.log_path,
            summary_path=DEFAULT_SUMMARY_PATH,
            scenario=request.scenario,
            stealth_mode=request.stealth_mode,
            mutation_profile=request.mutation_profile,
            initial_state=initial_state,
            memory_compaction_interval=request.memory_compaction_interval if request.memory_enabled else 0,
            memory_proxy_size=request.memory_proxy_size,
            memory_path=request.memory_path if request.memory_enabled else None,
            round_callback=on_round,
        )
    st.cache_data.clear()
    progress_slot.progress(1.0, text=f"Mission complete | {len(logs)} rounds committed")
    st.sidebar.success(f"{len(logs)} rounds committed")
    with st.sidebar.expander("Run summary", expanded=False):
        st.json(run_summary)
    return logs, run_summary


def _live_signal_html(entry: dict[str, Any], partial_logs: list[dict[str, Any]]) -> str:
    score = entry["score"]
    threats = len(entry.get("threats", []))
    actions = len(entry.get("defense_actions", []))
    detection = "DETECTED" if score.get("detection_success") else "MISSED"
    effect = "LANDED" if score.get("attack_success") else "BLOCKED"
    return (
        '<div class="live-signal">'
        f'<span>FRAME <strong>{entry["round"]:02d}</strong></span>'
        f'<span>ATTACK <strong>{_text(entry["attack"]["name"])}</strong></span>'
        f'<span>{_text(detection)}</span>'
        f'<span>{_text(effect)}</span>'
        f'<span>THREATS <strong>{threats}</strong></span>'
        f'<span>ACTIONS <strong>{actions}</strong></span>'
        f'<span>BUFFER <strong>{len(partial_logs)}</strong></span>'
        "</div>"
    )


# --------------------------------------------------------------------------- #
#  Top shell
# --------------------------------------------------------------------------- #
def _render_command_bar(
    logs: list[dict[str, Any]],
    summary: dict[str, Any],
    hash_valid: bool,
    log_path: Path,
) -> None:
    latest = logs[-1] if logs else {}
    status = "LIVE TELEMETRY" if logs else "STANDBY"
    chain = "CHAIN VERIFIED" if hash_valid else "CHAIN PENDING"
    scenario = latest.get("scenario") or summary.get("scenario", "no scenario")
    runner = summary.get("runner", "run_simulation")
    target = (latest.get("attack") or {}).get("target_domain", "no target")
    frames = len(logs)
    availability = summary.get("final_availability")
    availability_text = f"{availability:.2f}" if isinstance(availability, int | float) else "--"

    st.markdown(
        f"""
        <section class="command-shell">
          <div class="shell-scan"></div>
          <div class="shell-left">
            <div class="eyebrow"><span class="status-dot"></span>{_text(status)} / {_text(chain)}</div>
            <div class="app-title">DAH<span>//</span>FLAWLESS</div>
            <div class="app-subtitle">Operations view for observed-world Red / Blue simulation</div>
          </div>
          <div class="shell-right">
            <div class="signal-stack">
              <div>FRAMES <strong>{frames:02d}</strong></div>
              <div>RUNNER <strong>{_text(str(runner)).upper()}</strong></div>
              <div>SCENARIO <strong>{_text(str(scenario)).upper()}</strong></div>
              <div>TARGET <strong>{_text(str(target)).upper()}</strong></div>
              <div>AVAIL <strong>{availability_text}</strong></div>
            </div>
            <div class="radar" aria-hidden="true">
              <i></i><b></b><em></em>
            </div>
          </div>
        </section>
        <div class="log-strip">
          <span>LOG</span>
          <strong>{_text(_display_path(log_path))}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_state(log_path: Path) -> None:
    st.markdown(
        f"""
        <section class="empty-state">
          <div class="empty-crosshair"></div>
          <div>
            <div class="empty-kicker">NO TELEMETRY LOADED</div>
            <h3>Run a mission or point the console at an existing JSONL log.</h3>
            <p>
              Use the left Mission Control panel to set seed, rounds, scenario, stealth mode,
              and log path. Current target path:
              <code>{_text(_display_path(log_path))}</code>
            </p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_metric_tiles(summary: dict[str, Any], hash_valid: bool, logs: list[dict[str, Any]]) -> None:
    latest = logs[-1]
    policy_correctness = _policy_correctness(summary, logs)
    tiles = [
        ("ROUNDS", str(summary.get("rounds", len(logs))), "episode frames", "#b8c2cf", 1.0),
        ("BLUE DETECTION", _pct(summary.get("detection_rate", 0.0)), "threats caught", "#4dd9a4", summary.get("detection_rate", 0.0)),
        ("RED EFFECT", _pct(summary.get("attack_success_rate", 0.0)), "mutations landed", "#ff4f3d", summary.get("attack_success_rate", 0.0)),
        ("GOAL SUCCESS", _pct(summary.get("goal_success_rate", 0.0)), "objective support", "#4f9cff", summary.get("goal_success_rate", 0.0)),
        ("MISSION IMPACT", _pct(summary.get("avg_mission_impact_score", 0.0)), "avg impact score", "#f6c04f", summary.get("avg_mission_impact_score", 0.0)),
        ("ZTA POLICY", _pct(policy_correctness), "decision fit", "#8fb7ff", policy_correctness),
        ("AVAILABILITY", _number(summary.get("final_availability")), "mission budget", "#f6c04f", summary.get("final_availability", 0.0)),
        ("HASH CHAIN", "OK" if hash_valid else "FAIL", "log integrity", "#4dd9a4" if hash_valid else "#ff4f3d", 1.0),
    ]
    tile_html = "".join(_metric_tile(*tile) for tile in tiles)
    tactic = (latest.get("red_tactic") or {}).get("strategy", "unknown")
    attack = (latest.get("attack") or {}).get("name", "unknown")
    winner = (latest.get("score") or {}).get("winner", "unknown")
    strip = (
        f"SEED {latest.get('seed', '--')} / LATEST R{latest.get('round', '--')} / "
        f"ATTACK {attack} / TACTIC {tactic} / WINNER {winner}"
    )
    st.markdown(
        f"""
        <section class="kpi-grid">{tile_html}</section>
        <div class="telemetry-ticker"><span>{_text(strip)}</span></div>
        """,
        unsafe_allow_html=True,
    )


def _render_ops_brief(
    logs: list[dict[str, Any]],
    summary: dict[str, Any],
    hash_valid: bool,
    selected_round: int,
) -> None:
    left, right = st.columns([1.45, 1.0])
    with left:
        _render_map_panel(logs, hash_valid, selected_round)
    with right:
        _render_brief_panel(logs, summary, hash_valid, selected_round)


def _render_map_panel(logs: list[dict[str, Any]], hash_valid: bool, selected_round: int) -> None:
    st.markdown(_map_panel_html(logs, hash_valid, selected_round=selected_round), unsafe_allow_html=True)


def _map_panel_html(
    logs: list[dict[str, Any]],
    hash_valid: bool,
    title: str = "THEATER MAP",
    selected_round: int | None = None,
) -> str:
    selected = _entry_for_round(logs, selected_round)
    points, route = _map_points(logs, selected_round=_round_number(selected))
    point_svg = "".join(
        f'<a class="node-link" href="?round={item["round"]}" target="_self" '
        f'aria-label="Inspect round {item["round"]}">'
        f'<g class="map-node {item["class"]}{" latest" if item["latest"] else ""}{" selected" if item["selected"] else ""}">'
        f'<circle class="node-halo" cx="{item["x"]}" cy="{item["y"]}" r="{item["halo"]}">'
        f'<title>{_attr(item["title"])}</title></circle>'
        f'<circle class="map-point" cx="{item["x"]}" cy="{item["y"]}" r="{item["radius"]}"/>'
        f'<text class="map-label" x="{item["label_x"]}" y="{item["label_y"]}">R{item["round"]:02d}</text>'
        "</g></a>"
        for item in points
    )
    route_points = " ".join(f'{item["x"]},{item["y"]}' for item in route)
    cross = next((item for item in points if item["selected"]), points[-1] if points else {"x": 50, "y": 28})
    target = (selected.get("attack") or {}).get("target_domain", "unknown")
    attack = (selected.get("attack") or {}).get("name", "unknown")
    integrity = "VERIFIED" if hash_valid else "BROKEN"
    selected_label = f'R{_round_number(selected):02d}'

    return f"""
        <section class="ops-panel map-panel">
          <div class="panel-head">
            <span>{_text(title)}</span>
            <strong>{_text(selected_label)} / {_text(str(target)).upper()} / CLICK NODE TO INSPECT</strong>
          </div>
          <div class="map-stage">
            <div class="map-reticle" style="--x:{cross["x"]}%; --y:{cross["y"]}%;"></div>
            <svg class="ops-map" viewBox="0 0 100 56" preserveAspectRatio="none" aria-hidden="true">
              <path class="land" d="M4 37 L10 31 L18 32 L25 25 L36 27 L45 20 L56 22 L68 14 L84 18 L96 11 L96 47 L84 45 L76 50 L62 47 L51 52 L40 48 L28 50 L18 44 L8 46 Z"/>
              <path class="coast" d="M4 37 L10 31 L18 32 L25 25 L36 27 L45 20 L56 22 L68 14 L84 18 L96 11"/>
              <path class="coast minor" d="M8 46 L18 44 L28 50 L40 48 L51 52 L62 47 L76 50 L84 45 L96 47"/>
              <polyline class="route-shadow" points="{_attr(route_points)}"/>
              <polyline class="route" points="{_attr(route_points)}"/>
              <polyline class="route-flow" points="{_attr(route_points)}"/>
              {point_svg}
              <line class="cross-line x" x1="0" y1="{cross["y"]}" x2="100" y2="{cross["y"]}"/>
              <line class="cross-line y" x1="{cross["x"]}" y1="0" x2="{cross["x"]}" y2="56"/>
            </svg>
            <div class="map-grid"></div>
            <div class="map-hud top-left">AREA PARAM / OBSERVED WORLD</div>
            <div class="map-hud top-right">HASH / {_text(integrity)}</div>
            <div class="map-hud bottom-left">VECTOR / {_text(str(attack)).upper()}</div>
            <div class="map-hud bottom-right"><span class="legend blue"></span>BLUE <span class="legend red"></span>RED</div>
            <div class="map-hud center-readout">44.0000 N | 120.5000 W</div>
          </div>
        </section>
        """


def _render_brief_panel(
    logs: list[dict[str, Any]],
    summary: dict[str, Any],
    hash_valid: bool,
    selected_round: int,
) -> None:
    selected = _entry_for_round(logs, selected_round)
    score = selected["score"]
    attack = selected["attack"]
    threats = selected.get("threats", [])
    actions = selected.get("defense_actions", [])
    risks = selected.get("mission_risks", [])
    tags = selected.get("situation_tags") or selected.get("red_situation_tags", [])
    step_count = selected.get("step_count", 1)
    termination = selected.get("termination_reason", "fixed_round")
    attrition = _attrition_evidence(selected)
    policy = selected.get("zta_policy") or {}
    policy_correct = policy.get("policy_decision_correctness")
    policy_tone = "good" if (_float_or_none(policy_correct) or 0.0) >= 0.75 else "warn"
    chain_class = "good" if hash_valid else "bad"

    st.markdown(
        f"""
        <section class="ops-panel brief-panel">
          <div class="panel-head">
            <span>OPERATOR BRIEF</span>
            <strong>ROUND {_round_number(selected):02d}</strong>
          </div>
          <div class="brief-grid">
            {_brief_item("Winner", score.get("winner", "--"), _winner_class(score.get("winner")))}
            {_brief_item("Attack", attack.get("name", "--"), "hot")}
            {_brief_item("Target", attack.get("target_domain", "--"), "neutral")}
            {_brief_item("Goal", _goal_id(selected), "neutral")}
            {_brief_item("Impact", _pct(_mission_impact_score(selected)), "warn")}
            {_brief_item("Attrition", "TRIGGERED" if attrition.get("triggered") else "CLEAR", "hot" if attrition.get("triggered") else "neutral")}
            {_brief_item("Steps", step_count, "neutral")}
            {_brief_item("Detection", "SUCCESS" if score.get("detection_success") else "MISSED", "good" if score.get("detection_success") else "bad")}
            {_brief_item("Recovery", "SUCCESS" if score.get("recovery_success") else "PENDING", "good" if score.get("recovery_success") else "warn")}
            {_brief_item("Policy", _pct(policy_correct), policy_tone)}
            {_brief_item("Hash", "VERIFIED" if hash_valid else "FAILED", chain_class)}
          </div>
          <div class="brief-line">
            <span>Threats</span><strong>{len(threats)}</strong>
            <span>Actions</span><strong>{len(actions)}</strong>
            <span>Risks</span><strong>{len(risks)}</strong>
          </div>
          <div class="summary-readout">Termination {_text(str(termination)).upper()}</div>
          <div class="tag-cloud">{_tag_cloud(tags[:10])}</div>
          <div class="summary-readout">
            Detection {_pct(summary.get("detection_rate", 0.0))} /
            Red effect {_pct(summary.get("attack_success_rate", 0.0))} /
            ZTA policy {_pct(summary.get("avg_policy_decision_correctness", policy_correct))} /
            Mission impact {_pct(summary.get("avg_mission_impact_score", 0.0))} /
            Defense cost {_number(attrition.get("round_defense_cost"))} /
            Min availability {_number(summary.get("min_availability"))}
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
#  Tabs
# --------------------------------------------------------------------------- #
def _render_overview(logs: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    left, right = st.columns([1.45, 1])
    with left:
        _section("Round results", "scan, compare, and sort the simulation frames")
        st.dataframe(_scoreboard_rows(logs), width="stretch", hide_index=True)
    with right:
        _section("Run summary", "aggregated scoring output")
        st.dataframe(_summary_rows(summary), width="stretch", hide_index=True)

    zta_rows = _zta_round_rows(logs)
    if zta_rows:
        _section("Zero Trust policy", "per-round observe use decisions")
        st.dataframe(zta_rows, width="stretch", hide_index=True)

    attack_counts = Counter(entry["attack"]["name"] for entry in logs)
    winner_counts = Counter(entry["score"]["winner"] for entry in logs)
    col1, col2 = st.columns(2)
    with col1:
        _section("Attack vectors", "frequency by Red action")
        st.bar_chart(dict(attack_counts))
    with col2:
        _section("Outcomes", "winner distribution")
        st.bar_chart(dict(winner_counts))

    if logs and logs[0].get("raw_world_source_hash"):
        _section("Raw world evidence", "source hash and feature scoring")
        cols = st.columns([1, 1])
        with cols[0]:
            st.json(
                {
                    "raw_world_source_hash": logs[0].get("raw_world_source_hash"),
                    "truth_model": logs[0].get("truth_model"),
                    "truth_storage_key": logs[0].get("truth_storage_key"),
                },
                expanded=False,
            )
        with cols[1]:
            st.json(logs[0].get("raw_world_feature_scores", {}), expanded=False)


def _render_timeline(logs: list[dict[str, Any]], selected_round: int) -> None:
    _section("Round timeline", "expand a frame to inspect threats, actions, and incident reports")
    for entry in reversed(logs):
        score = entry["score"]
        title = (
            f'R{entry["round"]:02d} | {entry["attack"]["name"]} | '
            f'{score["winner"]} | avail {score["availability"]:.2f}'
        )
        with st.expander(title, expanded=_round_number(entry) == selected_round):
            cols = st.columns([1, 1, 1, 1, 1])
            cols[0].metric("Target", entry["attack"]["target_domain"])
            cols[1].metric("Threats", len(entry["threats"]))
            cols[2].metric("Actions", len(entry["defense_actions"]))
            cols[3].metric("Availability", f'{score["availability"]:.2f}')
            cols[4].metric("Impact", _pct(_mission_impact_score(entry)))

            st.markdown("**Situation tags**")
            st.markdown(_tag_cloud(entry.get("situation_tags") or entry.get("red_situation_tags", [])), unsafe_allow_html=True)
            if entry.get("red_situation_tag_details"):
                with st.popover("Red tag details"):
                    st.json(entry["red_situation_tag_details"])
            if entry.get("log_memory_event"):
                with st.popover("Rolling memory event"):
                    st.json(entry["log_memory_event"])
            if _attrition_evidence(entry):
                with st.popover("Attrition evidence"):
                    st.json(_attrition_evidence(entry))

            tcol, acol = st.columns(2)
            with tcol:
                st.markdown("**Threats**")
                st.dataframe(_threat_rows(entry), width="stretch", hide_index=True)
            with acol:
                st.markdown("**Defense actions**")
                st.dataframe(_action_rows(entry), width="stretch", hide_index=True)

            if entry.get("combat_steps"):
                st.markdown("**Combat steps**")
                st.dataframe(_combat_step_rows(entry), width="stretch", hide_index=True)

            zta_rows = _zta_timeline_rows(entry)
            if zta_rows:
                st.markdown("**Policy decision timeline**")
                st.dataframe(zta_rows, width="stretch", hide_index=True)

            st.markdown("**Incident report**")
            st.json(entry["incident_report"], expanded=False)


def _render_diff(logs: list[dict[str, Any]]) -> None:
    _section("Scorer / Admin diff", 'trusted state["world"] vs Blue observed state')
    st.caption('This view is scorer evidence. Blue Agent input remains redacted from state["world"].')
    for entry in reversed(logs):
        evidence = entry["score"]["evidence"]
        mismatch = evidence.get("mismatch")
        status = "MISMATCH" if mismatch else "MATCH"
        with st.expander(f'R{entry["round"]:02d} | {entry["attack"]["name"]} | {status}', expanded=False):
            left, right = st.columns(2)
            with left:
                st.markdown("**Trusted value**")
                st.json(evidence.get("trusted_value"), expanded=True)
            with right:
                st.markdown("**Observed value**")
                st.json(evidence.get("observed_value"), expanded=True)
            st.dataframe(
                [
                    {"field": "target_domain", "value": _compact(entry["attack"]["target_domain"])},
                    {"field": "mismatch", "value": _compact(mismatch)},
                    {"field": "truth_model", "value": _compact(evidence.get("truth_model"))},
                    {"field": "truth_storage_key", "value": _compact(evidence.get("truth_storage_key"))},
                    {"field": "blue_input_redacted", "value": _compact(entry.get("blue_input_redacted"))},
                ],
                width="stretch",
                hide_index=True,
            )


def _render_charts(logs: list[dict[str, Any]]) -> None:
    _section("Mission availability", "availability over simulation frames")
    st.line_chart(
        [{"round": entry["round"], "availability": entry["score"]["availability"]} for entry in logs],
        x="round",
        y="availability",
    )
    _section("Mission impact", "rule-based impact score over frames")
    st.line_chart(
        [{"round": entry["round"], "mission_impact": _mission_impact_score(entry)} for entry in logs],
        x="round",
        y="mission_impact",
    )

    policy_rows = [
        {
            "round": entry["round"],
            "policy_decision_correctness": (entry.get("zta_policy") or {}).get("policy_decision_correctness"),
        }
        for entry in logs
        if (entry.get("zta_policy") or {}).get("policy_decision_correctness") is not None
    ]
    if policy_rows:
        _section("ZTA policy correctness", "restrict attacked domain without overblocking clean domains")
        st.line_chart(policy_rows, x="round", y="policy_decision_correctness")

    col1, col2, col3 = st.columns(3)
    with col1:
        _section("Detection", "caught vs missed")
        st.bar_chart(
            {
                "detected": sum(1 for entry in logs if entry["score"]["detection_success"]),
                "missed": sum(1 for entry in logs if not entry["score"]["detection_success"]),
            }
        )
    with col2:
        _section("Attack outcome", "landed vs blocked")
        st.bar_chart(
            {
                "success": sum(1 for entry in logs if entry["score"]["attack_success"]),
                "blocked": sum(1 for entry in logs if not entry["score"]["attack_success"]),
            }
        )
    with col3:
        _section("Recovery", "successful recovery")
        st.bar_chart(
            {
                "recovered": sum(1 for entry in logs if entry["score"].get("recovery_success")),
                "pending": sum(1 for entry in logs if not entry["score"].get("recovery_success")),
            }
        )

    zta_counts = _zta_decision_counts(logs)
    if zta_counts:
        _section("ZTA decisions", "decision bands across rounds and combat steps")
        st.bar_chart(zta_counts)


def _render_decisions(logs: list[dict[str, Any]]) -> None:
    _section("Agent decision log", "agent events, reasons, and compact state deltas")
    for entry in reversed(logs):
        with st.expander(f'R{entry["round"]:02d} | decision chain', expanded=False):
            st.dataframe(_decision_rows(entry), width="stretch", hide_index=True)
            with st.popover("Raw JSON"):
                st.json(entry["decision_log"], expanded=False)


# --------------------------------------------------------------------------- #
#  Row builders
# --------------------------------------------------------------------------- #
def _scoreboard_rows(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "round": entry["round"],
            "attack": entry["attack"]["name"],
            "target": entry["attack"]["target_domain"],
            "goal": _goal_id(entry),
            "winner": entry["score"]["winner"],
            "attack_success": entry["score"]["attack_success"],
            "goal_success": entry["score"].get("goal_success"),
            "detection_success": entry["score"]["detection_success"],
            "recovery_success": entry["score"].get("recovery_success"),
            "availability": entry["score"]["availability"],
            "goal_reward": entry["score"].get("goal_reward"),
            "mission_impact": _mission_impact_score(entry),
            "policy_correctness": (entry.get("zta_policy") or {}).get("policy_decision_correctness"),
            "attrition": _attrition_evidence(entry).get("triggered"),
            "defense_cost": _attrition_evidence(entry).get("round_defense_cost"),
            "steps": entry.get("step_count"),
            "termination": entry.get("termination_reason"),
        }
        for entry in logs
    ]


def _summary_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    priority = [
        "rounds",
        "detection_rate",
        "attack_success_rate",
        "goal_success_rate",
        "final_availability",
        "min_availability",
        "attack_entropy",
        "tactic_entropy",
        "avg_goal_reward",
        "avg_mission_impact_score",
        "avg_policy_decision_correctness",
        "zta_decision_counts",
        "high_mission_impact_count",
        "avg_causal_consistency",
        "causal_warning_count",
        "causal_failure_count",
        "runner",
        "avg_step_count",
    ]
    keys = [key for key in priority if key in summary]
    keys.extend(key for key in summary if key not in keys)
    return [{"metric": key, "value": _compact(summary.get(key))} for key in keys]


def _threat_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "target": threat["target"],
            "confidence": threat["confidence"],
            "tags": ", ".join(threat["tags"]),
            "evidence": " | ".join(threat["evidence"]),
        }
        for threat in entry["threats"]
    ]


def _action_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "action": action["action"],
            "target": action["target"],
            "priority": action["priority"],
            "cost": action["availability_cost"],
            "status": action["status"],
        }
        for action in entry["defense_actions"]
    ]


def _zta_round_rows(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in logs:
        policy = entry.get("zta_policy") or {}
        per_domain = policy.get("per_domain") or {}
        if not policy and not per_domain:
            continue
        domain_scores = {
            domain: f'{item.get("decision")}:{_number(item.get("trust_score"))}'
            for domain, item in sorted(per_domain.items())
        }
        restricted = [domain for domain, item in sorted(per_domain.items()) if item.get("restricted")]
        rows.append(
            {
                "round": entry.get("round"),
                "attack_target": policy.get("attack_target_domain"),
                "correctness": policy.get("policy_decision_correctness"),
                "restricted_domains": ", ".join(restricted) if restricted else "-",
                "decision_counts": _compact(policy.get("decision_counts", {})),
                "domain_scores": _compact(domain_scores),
            }
        )
    return rows


def _combat_step_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for step in entry.get("combat_steps", []):
        score = step.get("step_score") or {}
        budgets = step.get("budgets") or {}
        rows.append(
            {
                "step": step.get("step"),
                "red_action": step.get("red_action"),
                "blue_action": step.get("blue_action"),
                "suspicion": _number(step.get("blue_suspicion")),
                "detected": step.get("detected_this_step"),
                "winner": score.get("winner"),
                "impact": _pct(_mission_impact_from_score(score)),
                "goal_reward": _number(score.get("goal_reward")),
                "red_budget": _number(budgets.get("red_budget")),
                "blue_compute": _number(budgets.get("blue_compute_budget")),
                "blue_power": _number(budgets.get("blue_power_budget")),
                "red_retries": budgets.get("red_retry_attempts"),
                "defense_cost": _number(budgets.get("blue_round_defense_cost")),
                "zta_min_trust": _number(_min_zta_trust(step.get("zta_decisions", []))),
                "zta_restrictive": _restrictive_zta_domains(step.get("zta_decisions", [])),
                "stable_steps": step.get("stable_steps"),
            }
        )

    return rows


def _zta_timeline_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    combat_steps = entry.get("combat_steps") or []
    if combat_steps:
        step_items = [(step.get("step"), step.get("zta_decisions", [])) for step in combat_steps]
    else:
        step_items = [(1, entry.get("zta_decisions", []))]

    for step_number, decisions in step_items:
        for item in decisions or []:
            rows.append(
                {
                    "step": step_number,
                    "domain": item.get("domain"),
                    "decision": item.get("decision"),
                    "trust_score": item.get("trust_score"),
                    "allowed_use": item.get("allowed_use"),
                    "restrictive": _is_restrictive_zta(item),
                    "reasons": ", ".join(str(reason) for reason in item.get("reasons", [])),
                }
            )
    return rows


def _decision_rows(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "agent": item.get("agent", "-") if isinstance(item, dict) else "-",
            "event": item.get("event", "-") if isinstance(item, dict) else "-",
            "reason": item.get("reason", "-") if isinstance(item, dict) else _compact(item),
            "after": _compact(item.get("after")) if isinstance(item, dict) else "-",
        }
        for item in entry["decision_log"]
    ]


def _goal_id(entry: dict[str, Any]) -> str:
    return str((entry.get("red_goal") or {}).get("goal_id") or entry.get("score", {}).get("goal_id") or "-")


def _mission_impact_score(entry: dict[str, Any]) -> float:
    return _mission_impact_from_score(entry.get("score") or {})


def _mission_impact_from_score(score: dict[str, Any]) -> float:
    evidence = score.get("evidence") or {}
    mission_impact = evidence.get("mission_impact") or {}
    value = mission_impact.get("mission_impact_score", score.get("mission_impact_score", 0.0))
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _attrition_evidence(entry: dict[str, Any]) -> dict[str, Any]:
    score = entry.get("score") or {}
    evidence = score.get("evidence") or {}
    attrition = evidence.get("attrition") or {}
    return attrition if isinstance(attrition, dict) else {}


def _policy_correctness(summary: dict[str, Any], logs: list[dict[str, Any]]) -> float:
    summary_value = _float_or_none(summary.get("avg_policy_decision_correctness"))
    if summary_value is not None:
        return summary_value
    values = [
        value
        for value in (
            _float_or_none((entry.get("zta_policy") or {}).get("policy_decision_correctness"))
            for entry in logs
        )
        if value is not None
    ]
    return round(sum(values) / len(values), 4) if values else 0.0


def _zta_decision_counts(logs: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter()
    for entry in logs:
        policy_counts = (entry.get("zta_policy") or {}).get("decision_counts")
        if policy_counts:
            counts.update(policy_counts)
            continue
        for item in _entry_zta_decisions(entry):
            decision = item.get("decision")
            if decision:
                counts[str(decision)] += 1
    return dict(sorted(counts.items()))


def _entry_zta_decisions(entry: dict[str, Any]) -> list[dict[str, Any]]:
    decisions = list(entry.get("zta_decisions", []) or [])
    for step in entry.get("combat_steps", []) or []:
        decisions.extend(step.get("zta_decisions", []) or [])
    return decisions


def _min_zta_trust(decisions: list[dict[str, Any]]) -> float | None:
    values = [_float_or_none(item.get("trust_score")) for item in decisions or []]
    values = [value for value in values if value is not None]
    return min(values) if values else None


def _restrictive_zta_domains(decisions: list[dict[str, Any]]) -> str:
    domains = sorted({str(item.get("domain")) for item in decisions or [] if _is_restrictive_zta(item)})
    return ", ".join(domains) if domains else "-"


def _is_restrictive_zta(item: dict[str, Any]) -> bool:
    return item.get("decision") in {"DOWNGRADE", "REVALIDATE", "QUARANTINE", "DENY"} or bool(
        item.get("restrictive")
    )


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
#  HTML helpers
# --------------------------------------------------------------------------- #
def _section(title: str, sub: str = "") -> None:
    subhtml = f'<span>{_text(sub)}</span>' if sub else ""
    st.markdown(
        f'<div class="section-label"><i></i><strong>{_text(title)}</strong>{subhtml}</div>',
        unsafe_allow_html=True,
    )


def _metric_tile(label: str, value: str, caption: str, color: str, amount: Any) -> str:
    meter = max(3, min(100, int(float(amount or 0) * 100)))
    return (
        f'<article class="kpi" style="--accent:{_attr(color)};--meter:{meter}%">'
        '<div class="kpi-top"><span></span>'
        f'<b>{_text(label)}</b></div>'
        f'<div class="kpi-value">{_text(value)}</div>'
        '<div class="kpi-meter"><i></i></div>'
        f'<div class="kpi-caption">{_text(caption)}</div>'
        "</article>"
    )


def _brief_item(label: str, value: Any, tone: str) -> str:
    return (
        f'<div class="brief-item {tone}">'
        f'<span>{_text(label)}</span>'
        f'<strong>{_text(str(value)).upper()}</strong>'
        "</div>"
    )


def _tag_cloud(tags: list[str]) -> str:
    if not tags:
        return '<div class="tag-cloud"><span>NO TAGS</span></div>'
    return "".join(f"<span>{_text(tag)}</span>" for tag in tags)


def _map_points(
    logs: list[dict[str, Any]],
    selected_round: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recent = logs[-10:]
    if selected_round is not None:
        selected_index = next(
            (index for index, entry in enumerate(logs) if _round_number(entry) == selected_round),
            None,
        )
        if selected_index is not None:
            start = max(0, min(selected_index - 4, max(0, len(logs) - 10)))
            recent = logs[start : start + 10]
    lanes = {
        "command": 15.0,
        "mission": 24.0,
        "telemetry": 34.0,
        "time": 40.0,
        "comms": 45.0,
    }
    points: list[dict[str, Any]] = []
    count = len(recent)
    for index, entry in enumerate(recent):
        attack = entry["attack"]["name"]
        target = entry["attack"]["target_domain"]
        score = entry["score"]
        seed = sum(ord(char) for char in attack + target) + entry["round"] * 19
        x = 50.0 if count == 1 else 8.0 + (index * (84.0 / (count - 1)))
        lane = lanes.get(str(target).lower(), 28.0)
        y = max(10.0, min(48.0, lane + ((seed % 9) - 4) * 0.8))
        latest = index == count - 1
        selected = _round_number(entry) == selected_round
        radius = 2.0 if latest else 1.25
        points.append(
            {
                "x": round(x, 2),
                "y": round(y, 2),
                "round": entry["round"],
                "class": _map_node_class(score.get("winner")),
                "title": f'R{entry["round"]} {attack} {score.get("winner")} impact {_pct(_mission_impact_score(entry))}',
                "latest": latest,
                "selected": selected,
                "radius": radius,
                "halo": 5.2 if latest else 3.2,
                "label_x": round(x + 1.7, 2),
                "label_y": round(y - 1.7, 2),
            }
        )
    return points, points


def _winner_class(winner: Any) -> str:
    if winner in {"BLUE", "BLUE_RECOVERY"}:
        return "good"
    if winner in {"RED_BREACH", "RED_ATTRITION"}:
        return "hot"
    return "neutral"


def _map_node_class(winner: Any) -> str:
    return "blue" if winner in {"BLUE", "BLUE_RECOVERY"} else "red"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _compact(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text[:157] + "..." if len(text) > 160 else text


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "--"


def _number(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "--"


def _text(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


# --------------------------------------------------------------------------- #
#  Visual shell
# --------------------------------------------------------------------------- #
def _inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
          --bg: #030405;
          --bg2: #07090c;
          --panel: rgba(9, 12, 16, .90);
          --panel2: rgba(15, 19, 25, .92);
          --line: rgba(203, 213, 225, .15);
          --line2: rgba(203, 213, 225, .28);
          --text: #d7dde5;
          --muted: #85909d;
          --faint: #59626e;
          --white: #f4f7fa;
          --red: #ff4f3d;
          --green: #4dd9a4;
          --amber: #f6c04f;
          --blue: #8fb7ff;
          --mono: "Cascadia Mono", "Consolas", "SFMono-Regular", ui-monospace, monospace;
          --display: "Bahnschrift", "Segoe UI Semibold", "Arial Narrow", var(--mono);
        }

        .stApp {
          background:
            linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px) 0 0 / 44px 44px,
            linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px) 0 0 / 44px 44px,
            linear-gradient(180deg, #050608 0%, #07090c 45%, #030405 100%);
          color: var(--text);
          font-family: var(--mono);
        }

        .stApp::before {
          content: "";
          position: fixed;
          inset: 0;
          pointer-events: none;
          background:
            repeating-linear-gradient(180deg, rgba(255,255,255,.035) 0 1px, transparent 1px 5px),
            linear-gradient(90deg, transparent, rgba(255,79,61,.045), transparent);
          mix-blend-mode: screen;
          opacity: .26;
          animation: staticShift 8s steps(6) infinite;
          z-index: 0;
        }

        @keyframes staticShift {
          0% { transform: translateY(0); }
          100% { transform: translateY(18px); }
        }

        header[data-testid="stHeader"] {
          background: transparent;
          pointer-events: auto;
          z-index: 999;
        }

        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        button[title="Open sidebar"],
        button[title="Close sidebar"],
        button[aria-label="Open sidebar"],
        button[aria-label="Close sidebar"] {
          display: inline-flex !important;
          visibility: visible !important;
          opacity: 1 !important;
          pointer-events: auto !important;
          z-index: 1000 !important;
        }

        div[data-testid="stToolbar"] {
          visibility: visible !important;
          pointer-events: auto !important;
        }
        .block-container {
          position: relative;
          z-index: 1;
          max-width: 1500px;
          padding: 1.05rem 1.8rem 3rem;
        }

        h1, h2, h3, h4, h5, h6 {
          font-family: var(--display) !important;
          letter-spacing: .02em;
          color: var(--white) !important;
        }

        p, div, span, label, td, th, code {
          font-family: var(--mono);
        }

        code {
          background: rgba(255,255,255,.06);
          border: 1px solid var(--line);
          border-radius: 2px;
          color: var(--white);
          padding: 2px 5px;
        }

        /* Sidebar */
        section[data-testid="stSidebar"] {
          background:
            linear-gradient(180deg, rgba(17,22,29,.98), rgba(5,7,10,.98)),
            linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px) 0 0 / 28px 28px;
          border-right: 1px solid var(--line2);
        }

        .side-brand {
          border: 1px solid var(--line2);
          background: rgba(0,0,0,.28);
          padding: 14px 14px 13px;
          margin: 2px 0 14px;
          position: relative;
          overflow: hidden;
        }

        .side-brand::after {
          content: "";
          position: absolute;
          left: -50%;
          top: 0;
          width: 45%;
          height: 100%;
          background: linear-gradient(90deg, transparent, rgba(255,255,255,.07), transparent);
          animation: sweep 6s linear infinite;
        }

        .side-kicker, .form-label {
          color: var(--muted);
          font-size: .68rem;
          letter-spacing: .18em;
          text-transform: uppercase;
        }

        .side-kicker span {
          display: inline-block;
          width: 7px;
          height: 7px;
          margin-right: 7px;
          border-radius: 50%;
          background: var(--green);
          box-shadow: 0 0 12px var(--green);
          animation: pulse 1.8s ease-in-out infinite;
        }

        .side-title {
          margin-top: 8px;
          color: var(--white);
          font-family: var(--display);
          font-size: 1.28rem;
          font-weight: 700;
          letter-spacing: .14em;
        }

        .side-sub {
          margin-top: 5px;
          color: var(--faint);
          font-size: .72rem;
        }

        .side-foot {
          display: grid;
          gap: 6px;
          margin-top: 16px;
          padding-top: 12px;
          border-top: 1px solid var(--line);
          color: var(--faint);
          font-size: .62rem;
          letter-spacing: .16em;
        }

        section[data-testid="stSidebar"] label p {
          color: var(--muted) !important;
          font-size: .72rem !important;
          letter-spacing: .08em;
        }

        section[data-testid="stSidebar"] input,
        section[data-testid="stSidebar"] [data-baseweb="select"] > div {
          background: #090d13 !important;
          border: 1px solid var(--line) !important;
          border-radius: 2px !important;
          color: var(--white) !important;
          font-family: var(--mono) !important;
        }

        /* Command shell */
        .command-shell {
          position: relative;
          display: flex;
          align-items: stretch;
          justify-content: space-between;
          gap: 22px;
          overflow: hidden;
          min-height: 142px;
          border: 1px solid var(--line2);
          background:
            linear-gradient(135deg, rgba(255,79,61,.10), transparent 28%),
            linear-gradient(180deg, rgba(13,17,23,.96), rgba(4,6,9,.96));
          box-shadow: inset 0 0 42px rgba(0,0,0,.42), 0 18px 48px rgba(0,0,0,.26);
          padding: 22px 24px;
        }

        .command-shell::before,
        .command-shell::after,
        .ops-panel::before,
        .ops-panel::after {
          content: "";
          position: absolute;
          width: 20px;
          height: 20px;
          border-color: var(--red);
          border-style: solid;
          opacity: .9;
        }

        .command-shell::before, .ops-panel::before {
          left: 9px;
          top: 9px;
          border-width: 1px 0 0 1px;
        }

        .command-shell::after, .ops-panel::after {
          right: 9px;
          bottom: 9px;
          border-width: 0 1px 1px 0;
        }

        .shell-scan {
          position: absolute;
          inset: 0 auto 0 -45%;
          width: 42%;
          background: linear-gradient(90deg, transparent, rgba(255,79,61,.13), transparent);
          animation: sweep 5.6s linear infinite;
        }

        @keyframes sweep {
          from { transform: translateX(0); }
          to { transform: translateX(360%); }
        }

        .shell-left, .shell-right {
          position: relative;
          z-index: 1;
        }

        .eyebrow {
          color: var(--muted);
          font-size: .75rem;
          letter-spacing: .18em;
          text-transform: uppercase;
        }

        .status-dot {
          display: inline-block;
          width: 8px;
          height: 8px;
          margin-right: 8px;
          border-radius: 50%;
          background: var(--green);
          box-shadow: 0 0 12px var(--green);
        }

        .app-title {
          margin-top: 8px;
          color: var(--white);
          font-family: var(--display);
          font-size: clamp(2rem, 4.6vw, 4.6rem);
          line-height: .92;
          font-weight: 800;
          letter-spacing: .08em;
          text-transform: uppercase;
          text-shadow: 0 0 28px rgba(255,79,61,.26);
        }

        .app-title span { color: var(--red); margin: 0 .1em; }

        .app-subtitle {
          margin-top: 12px;
          color: var(--muted);
          max-width: 620px;
          font-size: .86rem;
          letter-spacing: .08em;
        }

        .shell-right {
          display: flex;
          align-items: center;
          gap: 20px;
          min-width: 380px;
          justify-content: flex-end;
        }

        .signal-stack {
          display: grid;
          gap: 8px;
          min-width: 230px;
          color: var(--muted);
          font-size: .66rem;
          letter-spacing: .14em;
          text-transform: uppercase;
          text-align: right;
        }

        .signal-stack strong {
          display: inline-block;
          min-width: 76px;
          color: var(--white);
          margin-left: 8px;
        }

        .radar {
          position: relative;
          width: 92px;
          height: 92px;
          border: 1px solid var(--line2);
          border-radius: 50%;
          background:
            linear-gradient(transparent 49%, var(--line) 49% 51%, transparent 51%),
            linear-gradient(90deg, transparent 49%, var(--line) 49% 51%, transparent 51%),
            radial-gradient(circle, transparent 28%, var(--line) 29% 30%, transparent 31% 53%, var(--line) 54% 55%, transparent 56%);
        }

        .radar i {
          position: absolute;
          inset: 50% 50% auto auto;
          width: 42px;
          height: 1px;
          background: var(--red);
          box-shadow: 0 0 12px var(--red);
          transform-origin: right center;
          animation: spin 3.4s linear infinite;
        }

        .radar b, .radar em {
          position: absolute;
          border-radius: 50%;
          transform: translate(-50%, -50%);
          left: 50%;
          top: 50%;
          display: block;
        }

        .radar b {
          width: 7px;
          height: 7px;
          background: var(--red);
          box-shadow: 0 0 13px var(--red);
        }

        .radar em {
          width: 22px;
          height: 22px;
          border: 1px solid rgba(255,79,61,.7);
          animation: ring 1.9s ease-out infinite;
        }

        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes ring { to { width: 70px; height: 70px; opacity: 0; } }
        @keyframes pulse { 50% { opacity: .35; transform: scale(.78); } }

        .log-strip, .telemetry-ticker {
          overflow: hidden;
          white-space: nowrap;
          border: 1px solid var(--line);
          border-top: 0;
          background: rgba(0,0,0,.22);
          color: var(--muted);
          padding: 8px 11px;
          font-size: .68rem;
          letter-spacing: .14em;
        }

        .log-strip span {
          color: var(--red);
          margin-right: 10px;
        }

        .log-strip strong {
          color: var(--text);
          font-weight: 500;
          letter-spacing: .04em;
        }

        /* KPI */
        .kpi-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 12px;
          margin: 16px 0 10px;
        }

        .kpi {
          position: relative;
          overflow: hidden;
          min-height: 132px;
          padding: 15px 15px 14px;
          border: 1px solid var(--line);
          background: linear-gradient(180deg, rgba(16,21,28,.92), rgba(7,10,14,.92));
          animation: rise .48s cubic-bezier(.2,.7,.3,1) both;
        }

        .kpi:nth-child(2) { animation-delay: .05s; }
        .kpi:nth-child(3) { animation-delay: .10s; }
        .kpi:nth-child(4) { animation-delay: .15s; }
        .kpi:nth-child(5) { animation-delay: .20s; }

        @keyframes rise {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }

        .kpi::before {
          content: "";
          position: absolute;
          left: 0;
          top: 0;
          width: 3px;
          height: 100%;
          background: var(--accent);
          box-shadow: 0 0 18px var(--accent);
        }

        .kpi-top {
          display: flex;
          align-items: center;
          gap: 8px;
          color: var(--muted);
          font-size: .68rem;
          letter-spacing: .14em;
        }

        .kpi-top span {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: var(--accent);
          box-shadow: 0 0 10px var(--accent);
        }

        .kpi-value {
          margin-top: 13px;
          color: var(--white);
          font-family: var(--display);
          font-size: clamp(1.6rem, 3vw, 2.45rem);
          font-weight: 800;
          line-height: 1;
        }

        .kpi-meter {
          height: 3px;
          margin-top: 14px;
          background: rgba(255,255,255,.08);
          overflow: hidden;
        }

        .kpi-meter i {
          display: block;
          width: var(--meter);
          height: 100%;
          background: var(--accent);
          box-shadow: 0 0 10px var(--accent);
          animation: grow .9s cubic-bezier(.2,.7,.3,1) both .25s;
        }

        @keyframes grow { from { width: 0; } }

        .kpi-caption {
          margin-top: 10px;
          color: var(--faint);
          font-size: .72rem;
          letter-spacing: .06em;
        }

        .telemetry-ticker {
          position: relative;
          border-top: 1px solid var(--line);
          margin-bottom: 16px;
        }

        .telemetry-ticker span {
          display: inline-block;
          animation: ticker 18s linear infinite;
        }

        .live-signal {
          display: flex;
          flex-wrap: wrap;
          gap: 7px;
          margin: 10px 0 16px;
          padding: 10px;
          border: 1px solid var(--line);
          background: rgba(5,7,10,.78);
          color: var(--muted);
          font-size: .68rem;
          letter-spacing: .10em;
          text-transform: uppercase;
        }

        .live-signal span {
          border: 1px solid rgba(203,213,225,.12);
          background: rgba(255,255,255,.035);
          padding: 6px 8px;
        }

        .live-signal strong {
          color: var(--white);
          font-weight: 700;
        }

        @keyframes ticker {
          0%, 12% { transform: translateX(0); }
          100% { transform: translateX(-18%); }
        }

        /* Ops panels */
        .ops-panel {
          position: relative;
          overflow: hidden;
          border: 1px solid var(--line2);
          background: var(--panel);
          min-height: 370px;
          margin-bottom: 14px;
        }

        .panel-head {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: center;
          border-bottom: 1px solid var(--line);
          padding: 10px 14px;
          color: var(--muted);
          font-size: .72rem;
          letter-spacing: .18em;
          text-transform: uppercase;
        }

        .panel-head strong {
          color: var(--white);
          font-weight: 600;
        }

        .map-stage {
          position: relative;
          height: 328px;
          overflow: hidden;
          background:
            linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px) 0 0 / 34px 34px,
            linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px) 0 0 / 34px 34px,
            #030405;
        }

        .map-stage::after {
          content: "";
          position: absolute;
          inset: 0;
          background: linear-gradient(180deg, transparent, rgba(255,255,255,.08), transparent);
          transform: translateY(-100%);
          animation: verticalScan 4.8s linear infinite;
          pointer-events: none;
        }

        @keyframes verticalScan {
          to { transform: translateY(110%); }
        }

        .ops-map {
          position: absolute;
          inset: 8px 8px 6px 8px;
          width: calc(100% - 16px);
          height: calc(100% - 14px);
        }

        .land {
          fill: rgba(255,255,255,.075);
          stroke: rgba(255,255,255,.16);
          stroke-width: .45;
        }

        .coast {
          fill: none;
          stroke: rgba(244,247,250,.72);
          stroke-width: .55;
          filter: drop-shadow(0 0 2px rgba(244,247,250,.25));
        }

        .coast.minor {
          stroke: rgba(244,247,250,.35);
          stroke-width: .35;
        }

        .route-shadow,
        .route,
        .route-flow {
          fill: none;
          vector-effect: non-scaling-stroke;
        }

        .route-shadow {
          stroke: rgba(0,0,0,.85);
          stroke-width: 3.2;
          stroke-linecap: round;
          stroke-linejoin: round;
        }

        .route {
          stroke: rgba(244,247,250,.62);
          stroke-width: 1.05;
          stroke-linecap: round;
          stroke-linejoin: round;
        }

        .route-flow {
          stroke: rgba(246,192,79,.96);
          stroke-width: 1.2;
          stroke-linecap: round;
          stroke-dasharray: 1.5 5;
          animation: dashFlow 1.4s linear infinite;
          filter: drop-shadow(0 0 3px rgba(246,192,79,.55));
        }

        @keyframes dashFlow {
          to { stroke-dashoffset: -13; }
        }

        .node-halo {
          fill: rgba(244,247,250,.04);
          stroke: rgba(244,247,250,.24);
          stroke-width: .35;
        }

        .node-link {
          cursor: pointer;
          text-decoration: none;
          outline: none;
        }

        .node-link:hover .node-halo,
        .map-node.selected .node-halo {
          fill: rgba(246,192,79,.13);
          stroke: rgba(246,192,79,.95);
          stroke-width: .55;
          filter: drop-shadow(0 0 4px rgba(246,192,79,.85));
        }

        .map-node.latest .node-halo {
          fill: rgba(255,79,61,.08);
          stroke: rgba(255,79,61,.64);
          animation: nodePing 1.6s ease-out infinite;
        }

        .map-node.latest.selected .node-halo {
          fill: rgba(246,192,79,.13);
          stroke: rgba(246,192,79,.95);
        }

        @keyframes nodePing {
          70%, 100% { opacity: .25; }
        }

        .map-point {
          stroke: #030405;
          stroke-width: .45;
        }

        .map-node.blue .map-point {
          fill: var(--green);
          filter: drop-shadow(0 0 3px rgba(77,217,164,.75));
        }

        .map-node.red .map-point {
          fill: var(--red);
          filter: drop-shadow(0 0 3px rgba(255,79,61,.75));
        }

        .map-node.selected .map-point {
          stroke: var(--amber);
          stroke-width: .75;
        }

        .map-label {
          fill: rgba(244,247,250,.82);
          font-size: 2.25px;
          letter-spacing: .2px;
          paint-order: stroke;
          stroke: rgba(0,0,0,.88);
          stroke-width: .75px;
        }

        .cross-line {
          stroke: rgba(255,79,61,.30);
          stroke-width: .22;
          stroke-dasharray: 1.2 2.3;
        }

        .map-reticle {
          position: absolute;
          left: var(--x);
          top: var(--y);
          width: 66px;
          height: 66px;
          transform: translate(-50%, -50%);
          border: 1px solid rgba(255,255,255,.18);
          border-radius: 50%;
          z-index: 2;
          pointer-events: none;
        }

        .map-reticle::before,
        .map-reticle::after {
          content: "";
          position: absolute;
          background: rgba(255,79,61,.74);
          box-shadow: 0 0 10px rgba(255,79,61,.55);
        }

        .map-reticle::before {
          left: 50%;
          top: -19px;
          width: 1px;
          height: 104px;
        }

        .map-reticle::after {
          top: 50%;
          left: -19px;
          width: 104px;
          height: 1px;
        }

        .map-hud {
          position: absolute;
          color: rgba(244,247,250,.68);
          font-size: .62rem;
          letter-spacing: .14em;
          text-transform: uppercase;
          z-index: 3;
        }

        .top-left { left: 16px; top: 16px; }
        .top-right { right: 16px; top: 16px; }
        .bottom-left { left: 16px; bottom: 14px; }
        .bottom-right { right: 16px; bottom: 14px; }
        .legend {
          display: inline-block;
          width: 7px;
          height: 7px;
          border-radius: 50%;
          margin: 0 4px 0 10px;
          vertical-align: -1px;
        }
        .legend.blue { background: var(--green); box-shadow: 0 0 8px rgba(77,217,164,.75); }
        .legend.red { background: var(--red); box-shadow: 0 0 8px rgba(255,79,61,.75); }
        .center-readout {
          left: 50%;
          top: 47%;
          transform: translate(-50%, -50%);
          color: var(--white);
          font-size: .86rem;
          text-shadow: 0 0 12px rgba(0,0,0,.8);
        }

        .brief-panel {
          padding-bottom: 14px;
        }

        .brief-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
          padding: 14px;
        }

        .brief-item {
          border: 1px solid var(--line);
          background: rgba(255,255,255,.035);
          padding: 11px 12px;
          min-height: 74px;
        }

        .brief-item span {
          display: block;
          color: var(--muted);
          font-size: .66rem;
          letter-spacing: .14em;
          text-transform: uppercase;
        }

        .brief-item strong {
          display: block;
          margin-top: 8px;
          color: var(--white);
          overflow-wrap: anywhere;
          line-height: 1.25;
          font-size: .85rem;
        }

        .brief-item.good { border-left: 3px solid var(--green); }
        .brief-item.hot { border-left: 3px solid var(--red); }
        .brief-item.warn { border-left: 3px solid var(--amber); }
        .brief-item.bad { border-left: 3px solid var(--red); background: rgba(255,79,61,.055); }
        .brief-item.neutral { border-left: 3px solid var(--blue); }

        .brief-line {
          display: grid;
          grid-template-columns: 1fr auto 1fr auto 1fr auto;
          gap: 9px;
          margin: 0 14px 12px;
          padding: 10px 0;
          border-top: 1px solid var(--line);
          border-bottom: 1px solid var(--line);
          color: var(--muted);
          font-size: .72rem;
          letter-spacing: .09em;
        }

        .brief-line strong {
          color: var(--white);
        }

        .tag-cloud {
          display: flex;
          flex-wrap: wrap;
          gap: 7px;
          padding: 0 14px;
        }

        .tag-cloud span {
          border: 1px solid var(--line);
          background: rgba(255,255,255,.045);
          color: var(--text);
          padding: 5px 7px;
          font-size: .66rem;
          letter-spacing: .05em;
        }

        .summary-readout {
          margin: 13px 14px 0;
          color: var(--muted);
          font-size: .72rem;
          letter-spacing: .08em;
        }

        .empty-state {
          position: relative;
          display: grid;
          grid-template-columns: 130px minmax(0, 1fr);
          gap: 24px;
          align-items: center;
          min-height: 260px;
          border: 1px dashed var(--line2);
          background: rgba(8,11,15,.8);
          padding: 28px;
          overflow: hidden;
        }

        .empty-kicker {
          color: var(--red);
          font-size: .72rem;
          letter-spacing: .18em;
          margin-bottom: 8px;
        }

        .empty-state h3 {
          margin: 0 0 10px;
          font-size: 1.35rem;
        }

        .empty-state p {
          color: var(--muted);
          line-height: 1.7;
          max-width: 780px;
        }

        .empty-crosshair {
          width: 112px;
          height: 112px;
          border: 1px solid var(--line2);
          border-radius: 50%;
          background:
            linear-gradient(transparent 49%, rgba(255,79,61,.55) 49% 51%, transparent 51%),
            linear-gradient(90deg, transparent 49%, rgba(255,79,61,.55) 49% 51%, transparent 51%);
          animation: spin 8s linear infinite;
        }

        /* Streamlit widgets */
        .section-label {
          display: flex;
          align-items: baseline;
          gap: 10px;
          margin: 18px 0 10px;
          color: var(--white);
          font-size: .94rem;
          letter-spacing: .10em;
          text-transform: uppercase;
        }

        .section-label i {
          width: 10px;
          height: 13px;
          background: var(--red);
          box-shadow: 0 0 12px rgba(255,79,61,.55);
        }

        .section-label span {
          color: var(--muted);
          font-size: .68rem;
          letter-spacing: .08em;
          text-transform: none;
        }

        .stTabs [data-baseweb="tab-list"] {
          gap: 3px;
          border-bottom: 1px solid var(--line2);
        }

        .stTabs [data-baseweb="tab"] {
          height: 42px;
          border: 1px solid var(--line);
          border-bottom: 0;
          border-radius: 0;
          background: rgba(7,10,14,.86);
          color: var(--muted);
          font-family: var(--display) !important;
          letter-spacing: .08em;
          font-size: .78rem;
        }

        .stTabs [aria-selected="true"] {
          color: var(--white) !important;
          background: rgba(16,21,28,.95) !important;
          border-color: rgba(255,79,61,.65) !important;
          box-shadow: inset 0 -2px 0 var(--red);
        }

        .stButton > button,
        .stFormSubmitButton > button,
        .stDownloadButton > button {
          border: 1px solid rgba(255,79,61,.85) !important;
          border-radius: 2px !important;
          background: linear-gradient(180deg, rgba(255,79,61,.18), rgba(255,79,61,.06)) !important;
          color: #ffe2de !important;
          font-family: var(--display) !important;
          letter-spacing: .12em;
          transition: transform .16s ease, box-shadow .16s ease, background .16s ease;
        }

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {
          background: var(--red) !important;
          color: #050505 !important;
          box-shadow: 0 0 22px rgba(255,79,61,.45) !important;
          transform: translateY(-1px);
        }

        [data-testid="stMetric"] {
          background: rgba(9,12,16,.82);
          border: 1px solid var(--line);
          border-left: 3px solid var(--red);
          padding: 12px;
        }

        [data-testid="stMetricLabel"] {
          color: var(--muted) !important;
        }

        [data-testid="stMetricValue"] {
          color: var(--white) !important;
          font-family: var(--display) !important;
        }

        [data-testid="stExpander"] {
          border: 1px solid var(--line) !important;
          border-radius: 2px !important;
          background: rgba(9,12,16,.84) !important;
          margin-bottom: 8px;
        }

        [data-testid="stExpander"] summary {
          color: var(--text) !important;
          letter-spacing: .05em;
        }

        [data-testid="stDataFrame"],
        [data-testid="stJson"],
        pre {
          border: 1px solid var(--line) !important;
          border-radius: 2px !important;
          background: rgba(5,7,10,.9) !important;
        }

        .stAlert {
          border-radius: 2px;
          border: 1px solid var(--line2);
        }

        ::-webkit-scrollbar { width: 9px; height: 9px; }
        ::-webkit-scrollbar-track { background: #050608; }
        ::-webkit-scrollbar-thumb { background: #1b232e; border: 1px solid var(--line); }

        @media (max-width: 1120px) {
          .command-shell,
          .shell-right {
            display: block;
            min-width: 0;
          }

          .shell-right {
            margin-top: 18px;
          }

          .signal-stack {
            text-align: left;
            margin-bottom: 14px;
          }

          .radar {
            display: none;
          }

          .kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 720px) {
          .block-container {
            padding-left: .85rem;
            padding-right: .85rem;
          }

          .kpi-grid,
          .brief-grid,
          .empty-state {
            grid-template-columns: 1fr;
          }

          .app-title {
            font-size: 2.2rem;
          }

          .brief-line {
            grid-template-columns: 1fr auto;
          }

          .map-hud.center-readout {
            display: none;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
