import { useMemo } from "react";
import { motion, useReducedMotion } from "motion/react";
import { ArrowLeft, ChartBar, Crosshair, Gauge, ShieldCheck } from "@phosphor-icons/react";
import { getReplay, getRun } from "../data";
import { buildResultProfile, type CountItem, type ResultBin } from "../results";
import { useReplayStore } from "../store/useReplayStore";
import type { WinnerSide } from "../types/replay";

const EASE = [0.23, 1, 0.32, 1] as const;

const SIDE_CLASS: Record<WinnerSide, string> = {
  BLUE: "bg-blue-def text-blue-def border-blue-def/50",
  RED: "bg-red-ops text-red-ops border-red-ops/50",
  DRAW: "bg-text-low text-text-mid border-white/18",
};

const DECISION_TONE: Record<string, string> = {
  ALLOW: "bg-ok",
  ALLOW_WITH_MONITOR: "bg-hud-active",
  DOWNGRADE: "bg-warn",
  REVALIDATE: "bg-blue-def",
  DENY: "bg-red-ops",
  QUARANTINE: "bg-red-ops",
  UNKNOWN: "bg-text-low",
};

function toneForDecision(decision: string): string {
  return DECISION_TONE[decision] ?? "bg-text-low";
}

function sideBar(side: WinnerSide): string {
  return SIDE_CLASS[side].split(" ")[0];
}

function leadPath(trend: ReturnType<typeof buildResultProfile>["trend"]): string {
  if (trend.length === 0) return "";
  const maxAbs = Math.max(1, ...trend.map((point) => Math.abs(point.lead)));
  return trend
    .map((point, index) => {
      const x = trend.length === 1 ? 0 : (index / (trend.length - 1)) * 100;
      const y = 50 - (point.lead / maxAbs) * 42;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function CountStack({ items, total }: { items: CountItem[]; total: number }) {
  return (
    <div className="flex h-3 overflow-hidden border border-white/10 bg-surface-0">
      {items.map((item) => (
        <div
          key={item.key}
          title={`${item.key}: ${item.count}`}
          className={
            item.key === "BLUE"
              ? "bg-blue-def"
              : item.key === "RED"
                ? "bg-red-ops"
                : item.key === "DRAW"
                  ? "bg-text-low"
                  : toneForDecision(item.key)
          }
          style={{ width: `${Math.max(1, (item.count / Math.max(1, total)) * 100)}%` }}
        />
      ))}
    </div>
  );
}

function DistributionRows({
  title,
  items,
  accent,
}: {
  title: string;
  items: CountItem[];
  accent: "attack" | "policy" | "goal";
}) {
  const total = Math.max(1, items.reduce((sum, item) => sum + item.count, 0));
  return (
    <section className="border border-white/12 bg-black/22 p-4 backdrop-blur-md">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-text-hi">{title}</h2>
        <span className="font-mono text-[10px] text-text-low">{total.toLocaleString()} events</span>
      </div>
      <div className="space-y-2">
        {items.slice(0, 8).map((item, index) => (
          <button
            key={item.key}
            className="group grid w-full grid-cols-[minmax(0,1fr)_72px] items-center gap-3 text-left"
            title={`${item.key}: ${item.count}`}
          >
            <div className="min-w-0">
              <div className="flex items-center justify-between gap-3">
                <span className="truncate font-mono text-[11px] uppercase text-text-hi">{item.key}</span>
                <span className="font-mono text-[10px] text-text-low">{Math.round(item.rate * 100)}%</span>
              </div>
              <div className="mt-1 h-2 bg-white/10">
                <div
                  className={
                    accent === "attack"
                      ? index % 3 === 0
                        ? "h-full bg-red-ops"
                        : index % 3 === 1
                          ? "h-full bg-warn"
                          : "h-full bg-hud-active"
                      : accent === "policy"
                        ? `h-full ${toneForDecision(item.key)}`
                        : "h-full bg-blue-def"
                  }
                  style={{ width: `${Math.max(2, item.rate * 100)}%` }}
                />
              </div>
            </div>
            <span className="text-right font-display text-lg font-semibold text-text-hi">{item.count}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function OutcomeRail({ bins, onSelect }: { bins: ResultBin[]; onSelect: (index: number) => void }) {
  return (
    <section className="border border-white/12 bg-black/22 p-4 backdrop-blur-md">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-text-hi">
          Round density
        </h2>
        <span className="font-mono text-[10px] text-text-low">{bins.length} bins</span>
      </div>
      <div className="grid h-28 grid-cols-[repeat(72,minmax(0,1fr))] items-end gap-px overflow-hidden border border-white/10 bg-surface-0 p-1 max-[900px]:grid-cols-[repeat(36,minmax(0,1fr))]">
        {bins.map((bin) => (
          <button
            key={`${bin.fromRound}-${bin.toRound}`}
            onClick={() => onSelect(bin.index)}
            title={`R${bin.fromRound}-R${bin.toRound} / ${bin.attackDominant} / ${bin.policyDominant}`}
            className={`${sideBar(bin.dominant)} min-h-2 transition-opacity hover:opacity-100`}
            style={{
              height: `${28 + Math.max(bin.blueRate, bin.redRate) * 72}%`,
              opacity: 0.28 + Math.max(bin.blueRate, bin.redRate) * 0.62,
            }}
          />
        ))}
      </div>
      <div className="mt-2 flex justify-between font-mono text-[10px] text-text-low">
        <span>R{bins[0]?.fromRound ?? 1}</span>
        <span>click any block to return to replay</span>
        <span>R{bins[bins.length - 1]?.toRound ?? 1}</span>
      </div>
    </section>
  );
}

export function ResultsPage() {
  const reduce = useReducedMotion();
  const runId = useReplayStore((s) => s.runId);
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const roundLimit = useReplayStore((s) => s.roundLimit);
  const showReplay = useReplayStore((s) => s.showReplay);
  const setRound = useReplayStore((s) => s.setRound);
  const run = getRun(runId);
  const replay = getReplay(runId);
  const profile = useMemo(
    () => buildResultProfile(replay, roundIdx, roundLimit),
    [replay, roundIdx, roundLimit],
  );
  const totalPolicy = Math.max(1, profile.policyItems.reduce((sum, item) => sum + item.count, 0));

  function jumpToRound(index: number) {
    setRound(index);
  }

  return (
    <motion.main
      className="dashboard-shell relative z-10 h-full overflow-y-auto text-text-hi"
      initial={reduce ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.28, ease: EASE }}
    >
      <div className="dashboard-backdrop" aria-hidden />
      <header className="sticky top-0 z-20 border-b border-white/14 bg-surface-0/82 px-4 py-3 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3">
          <button
            onClick={showReplay}
            className="flex h-9 items-center gap-2 border border-white/12 px-3 font-display text-xs font-semibold uppercase tracking-[0.1em] text-text-mid transition-colors hover:border-hud-active hover:text-text-hi active:scale-[0.98]"
          >
            <ArrowLeft size={15} />
            Replay
          </button>
          <div className="min-w-0 flex-1">
            <p className="font-display text-xl font-bold uppercase tracking-[0.08em] text-white">
              Combat result board
            </p>
            <p className="truncate font-mono text-[10px] uppercase text-text-low">
              S{run.seed} / {run.scenarioLabel} / {profile.visibleRounds.toLocaleString()} rounds / current R
              {profile.currentRound}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-1.5">
            {profile.winnerItems.map((item) => (
              <div key={item.key} className={`min-w-24 border px-3 py-1.5 ${SIDE_CLASS[item.key as WinnerSide]}`}>
                <p className="font-mono text-[9px] uppercase opacity-75">{item.key}</p>
                <p className="font-display text-lg font-semibold text-text-hi">{item.count}</p>
              </div>
            ))}
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1440px] gap-3 px-4 py-4">
        <section className="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="border border-white/12 bg-black/22 p-4 backdrop-blur-md">
            <div className="mb-3 flex items-start justify-between gap-4">
              <div>
                <p className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-text-hi">
                  Cumulative lead curve
                </p>
                <p className="mt-1 max-w-xl text-xs leading-5 text-text-mid">
                  RED and BLUE are accumulated across the selected run. The center line is the tie boundary.
                </p>
              </div>
              <ChartBar size={22} className="text-hud-active" />
            </div>
            <svg viewBox="0 0 100 100" className="h-64 w-full border border-white/10 bg-surface-0/70">
              <line x1="0" x2="100" y1="50" y2="50" stroke="rgba(255,255,255,.18)" strokeWidth="0.5" />
              <path d={leadPath(profile.trend)} fill="none" stroke="rgb(95,212,245)" strokeWidth="1.3" />
              <path d={leadPath(profile.trend)} fill="none" stroke="rgba(95,212,245,.22)" strokeWidth="5" />
            </svg>
            <div className="mt-3 grid grid-cols-4 gap-2">
              {[
                ["FIRST BLUE", profile.firstBlueRound],
                ["RED PEAK", profile.redPeakRound],
                ["SHIFT", profile.shiftRound],
                ["BLUE PEAK", profile.bluePeakRound],
              ].map(([label, round]) => (
                <button
                  key={String(label)}
                  onClick={() => typeof round === "number" && jumpToRound(round - 1)}
                  className="border border-white/12 bg-white/[0.035] px-3 py-2 text-left transition-colors hover:border-hud-active hover:bg-hud-active/10"
                >
                  <p className="font-display text-[10px] font-semibold uppercase text-text-low">{label}</p>
                  <p className="mt-1 font-mono text-sm text-text-hi">{round ? `R${round}` : "pending"}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3">
            <section className="border border-white/12 bg-black/22 p-4 backdrop-blur-md">
              <div className="mb-3 flex items-center gap-2">
                <Gauge size={20} className="text-hud-active" />
                <h2 className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-text-hi">
                  Outcome split
                </h2>
              </div>
              <CountStack items={profile.winnerItems} total={profile.visibleRounds} />
              <div className="mt-3 grid grid-cols-3 gap-2">
                {profile.winnerItems.map((item) => (
                  <div key={item.key} className={`border p-3 ${SIDE_CLASS[item.key as WinnerSide]}`}>
                    <p className="font-mono text-[10px] uppercase opacity-75">{item.key}</p>
                    <p className="mt-1 font-display text-2xl font-semibold text-text-hi">{item.count}</p>
                    <p className="font-mono text-[10px] opacity-75">{Math.round(item.rate * 100)}%</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="border border-white/12 bg-black/22 p-4 backdrop-blur-md">
              <h2 className="mb-3 font-display text-sm font-semibold uppercase tracking-[0.12em] text-text-hi">
                Momentum windows
              </h2>
              <div className="grid gap-2">
                {profile.windows.map((window) => (
                  <button
                    key={`${window.label}-${window.fromRound}`}
                    onClick={() => jumpToRound(window.index)}
                    className={`border px-3 py-2 text-left transition-colors hover:border-hud-active ${
                      window.side === "BLUE"
                        ? "border-blue-def/45 bg-blue-def/10"
                        : "border-red-ops/45 bg-red-ops/10"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-display text-[11px] font-semibold uppercase text-text-hi">
                        {window.label}
                      </span>
                      <span className="font-mono text-[10px] text-text-low">
                        R{window.fromRound}-R{window.toRound}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-[10px] text-text-mid">{window.detail}</p>
                  </button>
                ))}
              </div>
            </section>
          </div>
        </section>

        <OutcomeRail bins={profile.bins} onSelect={jumpToRound} />

        <section className="grid gap-3 lg:grid-cols-3">
          <DistributionRows title="Attack selection" items={profile.attackItems} accent="attack" />
          <DistributionRows title="Goal selection" items={profile.goalItems} accent="goal" />
          <DistributionRows title="Policy decisions" items={profile.policyItems} accent="policy" />
        </section>

        <section className="border border-white/12 bg-black/22 p-4 backdrop-blur-md">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <ShieldCheck size={20} className="text-blue-def" />
              <Crosshair size={20} className="text-red-ops" />
              <h2 className="font-display text-sm font-semibold uppercase tracking-[0.12em] text-text-hi">
                Domain policy matrix
              </h2>
            </div>
            <span className="font-mono text-[10px] text-text-low">{totalPolicy.toLocaleString()} policy events</span>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            {profile.policyRows.map((row) => (
              <div key={row.domain} className="border border-white/10 bg-surface-0/60 p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="font-display text-xs font-semibold uppercase tracking-[0.12em] text-text-hi">
                    {row.domain}
                  </p>
                  <p className="font-mono text-[10px] text-text-low">{row.total}</p>
                </div>
                <CountStack items={row.decisions} total={row.total} />
                <div className="mt-3 space-y-1.5">
                  {row.decisions.map((item) => (
                    <div key={item.key} className="flex items-center justify-between gap-3">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className={`h-2 w-2 shrink-0 ${toneForDecision(item.key)}`} />
                        <span className="truncate font-mono text-[10px] uppercase text-text-mid">{item.key}</span>
                      </span>
                      <span className="font-mono text-[10px] text-text-low">{item.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </motion.main>
  );
}
