import { useEffect, useMemo, useState } from "react";
import { getReplay, getRun } from "../data";
import { buildLearningProfile, MAX_LEARNING_ROUNDS, type LearningBin, type LearningWindow } from "../learning";
import { useReplayStore } from "../store/useReplayStore";
import type { WinnerSide } from "../types/replay";

const SIDE_TEXT: Record<WinnerSide, string> = {
  BLUE: "text-blue-def",
  RED: "text-red-ops",
  DRAW: "text-text-mid",
};

const SIDE_BORDER: Record<WinnerSide, string> = {
  BLUE: "border-blue-def/55 bg-blue-def/10",
  RED: "border-red-ops/55 bg-red-ops/10",
  DRAW: "border-hud bg-white/[0.035]",
};

function binColor(bin: LearningBin): string {
  if (bin.dominant === "BLUE") return "bg-blue-def";
  if (bin.dominant === "RED") return "bg-red-ops";
  return "bg-text-low";
}

function binTitle(bin: LearningBin): string {
  return `R${bin.fromRound}-R${bin.toRound} · BLUE ${(bin.blueRate * 100).toFixed(0)}% / RED ${(bin.redRate * 100).toFixed(0)}%`;
}

function sideFill(side: WinnerSide): string {
  if (side === "BLUE") return "bg-blue-def";
  if (side === "RED") return "bg-red-ops";
  return "bg-text-low";
}

function windowTone(window: LearningWindow): string {
  if (window.side === "BLUE") return "border-blue-def/55 bg-blue-def/10 text-blue-def";
  if (window.side === "RED") return "border-red-ops/55 bg-red-ops/10 text-red-ops";
  return "border-white/15 bg-white/[0.035] text-text-mid";
}

interface LearningPathProps {
  runId: string;
  roundIdx: number;
  onSelectRound: (idx: number) => void;
}

export function LearningPath({ runId, roundIdx, onSelectRound }: LearningPathProps) {
  const replay = getReplay(runId);
  const run = getRun(runId);
  const roundLimit = useReplayStore((s) => s.roundLimit);
  const setRoundLimit = useReplayStore((s) => s.setRoundLimit);
  const requestedLimit = Math.min(Math.max(roundLimit, 1), MAX_LEARNING_ROUNDS);
  const profile = useMemo(() => buildLearningProfile(replay, roundIdx, roundLimit), [replay, roundIdx, roundLimit]);
  const currentRound = replay.rounds[roundIdx];
  const firstBlue = profile.firstBlueIndex === null ? null : replay.rounds[profile.firstBlueIndex];
  const shift = profile.shiftIndex === null ? null : replay.rounds[profile.shiftIndex];
  const currentTotal = Math.max(1, profile.currentCounts.BLUE + profile.currentCounts.RED + profile.currentCounts.DRAW);
  const currentLead = profile.currentCounts.BLUE - profile.currentCounts.RED;
  const leader = currentLead > 0 ? "BLUE" : currentLead < 0 ? "RED" : "DRAW";
  const [jumpValue, setJumpValue] = useState(String(currentRound?.round ?? 1));
  const [limitValue, setLimitValue] = useState(String(roundLimit));

  useEffect(() => {
    setJumpValue(String(currentRound?.round ?? 1));
  }, [currentRound?.round]);

  useEffect(() => {
    setLimitValue(String(roundLimit));
  }, [roundLimit]);

  function commitJump() {
    const wanted = Number(jumpValue);
    const nextIndex = replay.rounds.findIndex((round) => round.round === wanted);
    if (Number.isFinite(wanted) && nextIndex >= 0 && nextIndex < profile.visibleRounds) {
      onSelectRound(nextIndex);
    } else {
      setJumpValue(String(currentRound?.round ?? 1));
    }
  }

  function commitLimit() {
    const wanted = Number(limitValue);
    if (Number.isFinite(wanted)) {
      setRoundLimit(wanted);
    } else {
      setLimitValue(String(roundLimit));
    }
  }

  return (
    <section className="min-w-[420px] flex-1 border-x border-white/10 bg-black/14 px-3 py-2 max-[1023px]:order-4 max-[1023px]:min-w-0 max-[1023px]:basis-full">
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-low">
            Learning path
          </p>
          <p className="truncate font-mono text-[10px] text-text-low">
            S{run.seed} · {run.scenarioLabel} · {profile.markerCount} snapshots ·{" "}
            {profile.visibleRounds} detail / {requestedLimit} requested · {MAX_LEARNING_ROUNDS} cap
            {profile.capped ? " · capped" : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              commitLimit();
            }}
            className="flex h-7 items-center border border-white/12 bg-surface-0/80"
          >
            <span className="px-1.5 font-mono text-[10px] text-text-low">N</span>
            <input
              value={limitValue}
              onChange={(event) => setLimitValue(event.target.value)}
              onBlur={commitLimit}
              inputMode="numeric"
              aria-label="표시 라운드 수"
              className="h-full w-14 bg-transparent pr-1 font-mono text-[11px] text-text-hi outline-none"
            />
          </form>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              commitJump();
            }}
            className="flex h-7 items-center border border-white/12 bg-surface-0/80"
          >
            <span className="px-1.5 font-mono text-[10px] text-text-low">R</span>
            <input
              value={jumpValue}
              onChange={(event) => setJumpValue(event.target.value)}
              onBlur={commitJump}
              inputMode="numeric"
              aria-label="라운드 직접 이동"
              className="h-full w-12 bg-transparent pr-1 font-mono text-[11px] text-text-hi outline-none"
            />
          </form>
          {/* phase 라벨은 재생 중 RED PRESSURE↔BLUE MOMENTUM 등으로 폭이 변한다.
              가장 긴 라벨을 invisible 고스트로 겹쳐 폭을 상수 고정 → 옆 입력창이 흔들리지 않는다. */}
          <div className="inline-grid place-items-center border border-hud-active/40 bg-hud-active/10 px-2 py-1 font-display text-[10px] font-semibold uppercase text-hud-active">
            <span aria-hidden className="invisible col-start-1 row-start-1 whitespace-nowrap">
              BLUE MOMENTUM
            </span>
            <span className="col-start-1 row-start-1 whitespace-nowrap">{profile.phase}</span>
          </div>
        </div>
      </div>

      <div className="relative mb-1.5 h-5 overflow-hidden border border-white/10 bg-surface-0/70">
        <div className="flex h-full items-end gap-px px-1 py-1" aria-hidden>
          {profile.bins.map((bin) => (
            <div
              key={`${bin.fromRound}-${bin.toRound}`}
              title={binTitle(bin)}
              className={`min-w-0 flex-1 ${binColor(bin)}`}
              style={{
                height: `${35 + Math.abs(bin.score) * 65}%`,
                opacity: 0.22 + Math.max(bin.blueRate, bin.redRate, bin.drawRate) * 0.62,
              }}
            />
          ))}
        </div>
        <div
          className="absolute bottom-0 top-0 w-px bg-hud-active shadow-[0_0_12px_rgba(95,212,245,0.9)]"
          style={{
            left: `${profile.visibleRounds <= 1 ? 0 : (roundIdx / (profile.visibleRounds - 1)) * 100}%`,
          }}
        />
      </div>

      <div className="mb-1.5 grid gap-1.5 sm:grid-cols-[1.1fr_0.9fr]">
        <div className="grid grid-cols-3 overflow-hidden border border-white/10 bg-surface-0/60">
          {(["BLUE", "RED", "DRAW"] as WinnerSide[]).map((side) => {
            const count = profile.currentCounts[side];
            const ratio = count / currentTotal;
            return (
              <div key={side} className="border-r border-white/8 px-2 py-1.5 last:border-r-0">
                <div className="flex items-center justify-between gap-2 font-mono text-[9px] text-text-low">
                  <span>{side}</span>
                  <span>{Math.round(ratio * 100)}%</span>
                </div>
                <div className="mt-1 h-1 bg-white/10">
                  <div className={`h-full ${sideFill(side)}`} style={{ width: `${Math.max(4, ratio * 100)}%` }} />
                </div>
                <p className={`mt-1 font-display text-[11px] font-semibold ${SIDE_TEXT[side]}`}>{count}</p>
              </div>
            );
          })}
        </div>
        <div className={`border px-2 py-1.5 ${SIDE_BORDER[leader]}`}>
          <div className="flex items-center justify-between gap-2 font-mono text-[9px] uppercase text-text-low">
            <span>current lead</span>
            <span>R{currentRound?.round ?? 1}</span>
          </div>
          <p className={`mt-1 font-display text-xs font-semibold ${SIDE_TEXT[leader]}`}>
            {leader === "DRAW" ? "EVEN" : `${leader} +${Math.abs(currentLead)}`}
          </p>
        </div>
      </div>

      <nav aria-label="Rolling momentum windows" className="mb-1.5 grid gap-1.5 sm:grid-cols-3">
        {profile.windows.map((window) => (
          <button
            key={`${window.label}-${window.fromRound}-${window.toRound}`}
            onClick={() => onSelectRound(window.index)}
            title={window.detail}
            className={`min-w-0 border px-2 py-1.5 text-left transition-colors hover:border-hud-active/70 hover:bg-white/8 ${windowTone(window)}`}
          >
            <span className="font-display text-[9px] font-semibold uppercase tracking-[0.1em]">{window.label}</span>
            <span className="mt-1 block truncate font-mono text-[10px] text-text-hi">
              R{window.fromRound}-R{window.toRound}
            </span>
            <span className="mt-0.5 block truncate font-mono text-[9px] text-text-low">{window.detail}</span>
          </button>
        ))}
      </nav>

      <nav aria-label="대표 라운드 스냅샷" className="flex gap-1 overflow-x-auto pb-0.5">
        {profile.markers.map((marker) => {
          const active = marker.index === roundIdx;
          return (
            <button
              key={`${marker.index}-${marker.kind}`}
              onClick={() => onSelectRound(marker.index)}
              title={marker.detail}
              aria-pressed={active}
              className={`grid h-9 min-w-16 content-center border px-2 text-left transition-colors ${
                active
                  ? "border-hud-active bg-hud-active/15 text-hud-active"
                  : `${SIDE_BORDER[marker.side]} hover:border-hud-active/60 hover:bg-white/8`
              }`}
            >
              <span className="font-mono text-[11px] leading-none">R{marker.round}</span>
              <span className={`mt-0.5 truncate font-display text-[8px] font-semibold uppercase leading-none ${active ? "text-hud-active" : SIDE_TEXT[marker.side]}`}>
                {marker.label}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="mt-1 flex items-center justify-between gap-3 font-mono text-[10px] text-text-low">
        <span className="truncate">
          {firstBlue ? `first BLUE R${firstBlue.round}` : "first BLUE pending"}
        </span>
        <span className="truncate text-right">
          {shift ? `shift R${shift.round} · ${shift.attack.target_domain}` : "shift pending"}
        </span>
      </div>
    </section>
  );
}
