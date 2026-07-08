from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "logs" / "round_logs.jsonl"
SUMMARY_PATH = ROOT / "data" / "logs" / "summary.json"
OUT_PATH = ROOT / "dist" / "index.html"


def _load_logs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _html_template() -> str:
    return (
        r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DAH // FLAWLESS</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07090d;
      --panel: #10151c;
      --panel-2: #151d26;
      --line: #263442;
      --text: #e8edf2;
      --muted: #9aa7b5;
      --red: #ef4c3b;
      --blue: #4f9cff;
      --green: #50d27c;
      --amber: #f5ba45;
      --ink: #05070a;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    button, input { font: inherit; }
    .app { min-height: 100vh; }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 18px clamp(18px, 4vw, 48px);
      background: rgba(7, 9, 13, 0.92);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(18px);
    }
    .brand { display: flex; align-items: center; gap: 14px; min-width: 0; }
    .mark {
      width: 42px;
      height: 42px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, var(--red), #f08137);
      color: white;
      font-weight: 900;
      border-radius: 8px;
    }
    h1 { margin: 0; font-size: clamp(20px, 3vw, 34px); line-height: 1.05; }
    .subtitle { margin-top: 5px; color: var(--muted); font-size: 13px; }
    .status-strip { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      min-height: 30px;
      padding: 6px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      background: #0b1016;
      font-size: 12px;
      white-space: nowrap;
    }
    .dot { width: 7px; height: 7px; border-radius: 99px; background: var(--green); }
    main { padding: 28px clamp(18px, 4vw, 48px) 52px; }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.8fr);
      gap: 22px;
      align-items: stretch;
      margin-bottom: 22px;
    }
    .brief {
      min-height: 260px;
      padding: clamp(22px, 4vw, 36px);
      border: 1px solid var(--line);
      background:
        radial-gradient(circle at 75% 20%, rgba(79, 156, 255, 0.14), transparent 34%),
        linear-gradient(135deg, #111820, #090c11 74%);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }
    .eyebrow { color: var(--amber); font-size: 12px; font-weight: 800; text-transform: uppercase; }
    .brief h2 { margin: 12px 0 14px; font-size: clamp(28px, 5vw, 54px); line-height: 1; }
    .brief p { margin: 0; color: #c6d0dc; max-width: 800px; line-height: 1.65; }
    .mini-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 24px; }
    .mini {
      padding: 14px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(255,255,255,0.04);
      border-radius: 8px;
    }
    .mini b { display: block; font-size: 23px; margin-bottom: 4px; }
    .mini span { color: var(--muted); font-size: 12px; }
    .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 15px 16px;
      border-bottom: 1px solid var(--line);
      background: #0d1218;
    }
    .panel-title { margin: 0; font-size: 14px; text-transform: uppercase; }
    .panel-sub { color: var(--muted); font-size: 12px; }
    .panel-body { padding: 16px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 22px;
    }
    .metric {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 15px;
      min-height: 116px;
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; }
    .metric strong { display: block; margin-top: 13px; font-size: clamp(25px, 4vw, 38px); line-height: 1; }
    .metric small { display: block; margin-top: 10px; color: #b5c0cc; }
    .grid-2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; margin-bottom: 18px; }
    .bar-list { display: grid; gap: 12px; }
    .bar-row { display: grid; grid-template-columns: minmax(110px, 170px) minmax(0, 1fr) 44px; gap: 10px; align-items: center; }
    .bar-label { color: #cbd4df; font-size: 12px; overflow-wrap: anywhere; }
    .track { height: 10px; background: #081018; border: 1px solid #1f2c38; border-radius: 999px; overflow: hidden; }
    .fill { height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--blue), var(--green)); }
    .bar-value { color: var(--muted); font-size: 12px; text-align: right; }
    .timeline { display: grid; gap: 12px; }
    .round {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 14px;
    }
    .round-top { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
    .round-title { font-weight: 800; }
    .round-meta { display: flex; flex-wrap: wrap; gap: 8px; color: var(--muted); font-size: 12px; }
    .winner-blue { color: var(--blue); }
    .winner-recovery { color: var(--green); }
    .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 11px; }
    .tag {
      padding: 5px 8px;
      border: 1px solid #2c3b49;
      border-radius: 999px;
      color: #bfd0df;
      background: #0c1219;
      font-size: 11px;
    }
    .controls {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 14px;
    }
    .search {
      min-height: 38px;
      flex: 1 1 260px;
      border: 1px solid var(--line);
      background: #0b1016;
      color: var(--text);
      border-radius: 8px;
      padding: 0 12px;
    }
    .seg {
      display: flex;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #090d12;
    }
    .seg button {
      border: 0;
      border-right: 1px solid var(--line);
      color: var(--muted);
      background: transparent;
      padding: 10px 12px;
      cursor: pointer;
    }
    .seg button:last-child { border-right: 0; }
    .seg button.active { color: var(--ink); background: var(--amber); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 11px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 11px; text-transform: uppercase; background: #0c1218; }
    td { color: #dce5ef; }
    .json-box {
      max-height: 460px;
      overflow: auto;
      margin: 0;
      padding: 16px;
      background: #080c11;
      border: 1px solid var(--line);
      border-radius: 8px;
      color: #cbd6e1;
      font-size: 12px;
      line-height: 1.5;
    }
    .footer {
      margin-top: 26px;
      color: var(--muted);
      font-size: 12px;
      text-align: center;
    }
    @media (max-width: 980px) {
      .hero, .grid-2 { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .topbar { align-items: flex-start; flex-direction: column; }
      .status-strip { justify-content: flex-start; }
    }
    @media (max-width: 620px) {
      .metrics, .mini-grid { grid-template-columns: 1fr; }
      .bar-row { grid-template-columns: 1fr; }
      .bar-value { text-align: left; }
      th:nth-child(4), td:nth-child(4) { display: none; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <div class="mark">DAH</div>
        <div>
          <h1>DAH // FLAWLESS</h1>
          <div class="subtitle">Red x Blue adversarial simulation static dashboard</div>
        </div>
      </div>
      <div class="status-strip">
        <span class="pill"><span class="dot"></span> Static HTML</span>
        <span class="pill">Scenario <b id="pillScenario"></b></span>
        <span class="pill">Updated <b>__GENERATED_AT__</b></span>
      </div>
    </header>

    <main>
      <section class="hero">
        <div class="brief">
          <div>
            <div class="eyebrow">Mission summary</div>
            <h2>Observe, attack, detect, recover.</h2>
            <p id="scenarioDescription"></p>
          </div>
          <div class="mini-grid">
            <div class="mini"><b id="roundCount">0</b><span>Rounds</span></div>
            <div class="mini"><b id="winnerLead">-</b><span>Dominant outcome</span></div>
            <div class="mini"><b id="mutationProfile">-</b><span>Mutation profile</span></div>
            <div class="mini"><b id="stealthMode">-</b><span>Red stealth mode</span></div>
          </div>
        </div>
        <aside class="panel">
          <div class="panel-head">
            <h3 class="panel-title">Final Trust State</h3>
            <span class="panel-sub">Blue policy</span>
          </div>
          <div class="panel-body">
            <div id="trustBars" class="bar-list"></div>
          </div>
        </aside>
      </section>

      <section class="metrics" id="metrics"></section>

      <section class="grid-2">
        <div class="panel">
          <div class="panel-head">
            <h3 class="panel-title">Attack Mix</h3>
            <span class="panel-sub">Selected attacks</span>
          </div>
          <div class="panel-body"><div id="attackBars" class="bar-list"></div></div>
        </div>
        <div class="panel">
          <div class="panel-head">
            <h3 class="panel-title">Goal Mix</h3>
            <span class="panel-sub">Red objectives</span>
          </div>
          <div class="panel-body"><div id="goalBars" class="bar-list"></div></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h3 class="panel-title">Round Timeline</h3>
          <span class="panel-sub">Filter and inspect each event</span>
        </div>
        <div class="panel-body">
          <div class="controls">
            <input id="search" class="search" type="search" placeholder="Search attack, goal, tactic, tag..." />
            <div class="seg" role="group" aria-label="timeline filter">
              <button class="active" data-filter="all">All</button>
              <button data-filter="BLUE">Blue</button>
              <button data-filter="BLUE_RECOVERY">Recovery</button>
            </div>
          </div>
          <div id="timeline" class="timeline"></div>
        </div>
      </section>

      <section class="grid-2" style="margin-top:18px">
        <div class="panel">
          <div class="panel-head">
            <h3 class="panel-title">Scoreboard</h3>
            <span class="panel-sub">Round-level metrics</span>
          </div>
          <div class="panel-body" style="overflow:auto">
            <table>
              <thead>
                <tr><th>Round</th><th>Attack</th><th>Goal</th><th>Winner</th><th>Availability</th><th>Reward</th></tr>
              </thead>
              <tbody id="scoreRows"></tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head">
            <h3 class="panel-title">Embedded Summary JSON</h3>
            <span class="panel-sub">For judges and reviewers</span>
          </div>
          <div class="panel-body">
            <pre class="json-box" id="summaryJson"></pre>
          </div>
        </div>
      </section>
      <div class="footer">This file is self-contained and can be uploaded with Netlify Drop.</div>
    </main>
  </div>

  <script id="dah-data" type="application/json">__DATA_JSON__</script>
  <script>
    const payload = JSON.parse(document.getElementById("dah-data").textContent);
    const logs = payload.logs || [];
    const summary = payload.summary || {};
    let activeFilter = "all";

    const fmtPercent = (value) => `${Math.round((Number(value || 0)) * 100)}%`;
    const fmtNumber = (value, digits = 3) => Number(value || 0).toFixed(digits).replace(/\.?0+$/, "");
    const byId = (id) => document.getElementById(id);
    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[char]));

    function barRows(data, colorClass = "") {
      const entries = Object.entries(data || {}).sort((a, b) => Number(b[1]) - Number(a[1]));
      const max = Math.max(1, ...entries.map(([, value]) => Number(value || 0)));
      if (!entries.length) return `<div class="panel-sub">No data</div>`;
      return entries.map(([label, value]) => {
        const width = Math.max(4, Math.round((Number(value || 0) / max) * 100));
        return `<div class="bar-row">
          <div class="bar-label">${escapeHtml(label)}</div>
          <div class="track"><div class="fill ${colorClass}" style="width:${width}%"></div></div>
          <div class="bar-value">${escapeHtml(value)}</div>
        </div>`;
      }).join("");
    }

    function trustRows(data) {
      const entries = Object.entries(data || {});
      if (!entries.length) return `<div class="panel-sub">No trust data</div>`;
      return entries.map(([label, value]) => {
        const width = Math.max(4, Math.min(100, Math.round(Number(value || 0) * 100)));
        return `<div class="bar-row">
          <div class="bar-label">${escapeHtml(label)}</div>
          <div class="track"><div class="fill" style="width:${width}%"></div></div>
          <div class="bar-value">${fmtPercent(value)}</div>
        </div>`;
      }).join("");
    }

    function renderMetrics() {
      const metrics = [
        ["Detection rate", fmtPercent(summary.detection_rate), "Blue correctly identified attacks"],
        ["Attack success", fmtPercent(summary.attack_success_rate), "Red effect reached scorer condition"],
        ["Goal success", fmtPercent(summary.goal_success_rate), "Goal-aware scorer result"],
        ["Availability", fmtPercent(summary.final_availability), "Final system availability"],
      ];
      byId("metrics").innerHTML = metrics.map(([label, value, help]) => `
        <div class="metric"><span>${label}</span><strong>${value}</strong><small>${help}</small></div>
      `).join("");
    }

    function roundMatches(entry, query) {
      if (activeFilter !== "all" && entry?.score?.winner !== activeFilter) return false;
      if (!query) return true;
      const haystack = [
        entry?.attack?.name,
        entry?.red_goal?.goal_id,
        entry?.red_tactic?.strategy,
        entry?.score?.winner,
        ...(entry?.situation_tags || []),
      ].join(" ").toLowerCase();
      return haystack.includes(query.toLowerCase());
    }

    function renderTimeline() {
      const query = byId("search").value.trim();
      const filtered = logs.filter((entry) => roundMatches(entry, query));
      byId("timeline").innerHTML = filtered.map((entry) => {
        const winner = entry?.score?.winner || "-";
        const tags = (entry?.situation_tags || []).slice(0, 12);
        return `<article class="round">
          <div class="round-top">
            <div class="round-title">Round ${escapeHtml(entry.round)} · ${escapeHtml(entry?.attack?.name)}</div>
            <div class="${winner === "BLUE_RECOVERY" ? "winner-recovery" : "winner-blue"}">${escapeHtml(winner)}</div>
          </div>
          <div class="round-meta">
            <span>Goal: ${escapeHtml(entry?.red_goal?.goal_id || entry?.score?.goal_id || "-")}</span>
            <span>Tactic: ${escapeHtml(entry?.red_tactic?.strategy || "-")}</span>
            <span>Availability: ${fmtPercent(entry?.score?.availability)}</span>
            <span>Reward: ${fmtNumber(entry?.score?.goal_reward)}</span>
          </div>
          <div class="tags">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
        </article>`;
      }).join("") || `<div class="panel-sub">No rounds match the current filter.</div>`;
    }

    function renderScoreRows() {
      byId("scoreRows").innerHTML = logs.map((entry) => `
        <tr>
          <td>${escapeHtml(entry.round)}</td>
          <td>${escapeHtml(entry?.attack?.name || "-")}</td>
          <td>${escapeHtml(entry?.red_goal?.goal_id || entry?.score?.goal_id || "-")}</td>
          <td>${escapeHtml(entry?.score?.winner || "-")}</td>
          <td>${fmtPercent(entry?.score?.availability)}</td>
          <td>${fmtNumber(entry?.score?.goal_reward)}</td>
        </tr>
      `).join("");
    }

    function init() {
      const winners = summary.winners || {};
      const winnerLead = Object.entries(winners).sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[0] || "-";
      byId("pillScenario").textContent = summary.scenario || "-";
      byId("scenarioDescription").textContent =
        summary?.scenario_profile?.description ||
        "Static export of the DAH Flawless Red/Blue simulation. Upload this single HTML file to Netlify Drop to share the result.";
      byId("roundCount").textContent = summary.rounds || logs.length || 0;
      byId("winnerLead").textContent = winnerLead;
      byId("mutationProfile").textContent = summary.mutation_profile || "-";
      byId("stealthMode").textContent = summary.stealth_mode || "-";
      byId("trustBars").innerHTML = trustRows(summary?.blue_policy_state?.domain_trust || {});
      byId("attackBars").innerHTML = barRows(summary.attacks || {});
      byId("goalBars").innerHTML = barRows(summary.goals || {});
      byId("summaryJson").textContent = JSON.stringify(summary, null, 2);
      renderMetrics();
      renderTimeline();
      renderScoreRows();
    }

    byId("search").addEventListener("input", renderTimeline);
    document.querySelectorAll("[data-filter]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll("[data-filter]").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        activeFilter = button.dataset.filter;
        renderTimeline();
      });
    });
    init();
  </script>
</body>
</html>
"""
    )


def main() -> None:
    logs = _load_logs(LOG_PATH)
    summary = _load_summary(SUMMARY_PATH)
    payload = {"summary": summary, "logs": logs}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = (
        _html_template()
        .replace("__DATA_JSON__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
        .replace("__GENERATED_AT__", generated_at)
    )
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
