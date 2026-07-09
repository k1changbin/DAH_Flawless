import { ChartBar, Pause, Play, SignOut, SkipBack, SkipForward } from "@phosphor-icons/react";
import { getRound, getRun, getStep } from "../data";
import { PLAYBACK_SPEEDS, useReplayStore, type PlaybackSpeed } from "../store/useReplayStore";
import type { WinnerSide } from "../types/replay";
import { LearningPath } from "./LearningPath";

const WINNER_STYLE: Record<WinnerSide, string> = {
  BLUE: "border-blue-def text-blue-def",
  RED: "border-red-ops text-red-ops",
  DRAW: "border-hud text-text-mid",
};

export function CommandBar() {
  const runId = useReplayStore((s) => s.runId);
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const playing = useReplayStore((s) => s.playing);
  const playbackSpeed = useReplayStore((s) => s.playbackSpeed);
  const setRound = useReplayStore((s) => s.setRound);
  const setPlaybackSpeed = useReplayStore((s) => s.setPlaybackSpeed);
  const togglePlay = useReplayStore((s) => s.togglePlay);
  const next = useReplayStore((s) => s.next);
  const prev = useReplayStore((s) => s.prev);
  const showResults = useReplayStore((s) => s.showResults);
  const exitToLanding = useReplayStore((s) => s.exitToLanding);

  const activeRun = getRun(runId);
  const round = getRound(runId, roundIdx);
  const step = getStep(runId, roundIdx, stepIdx);
  const total = round.timeline.length;
  const side = round.outcome.winner_side;

  return (
    <header className="dashboard-bar relative z-10 flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b border-white/14 px-4 py-2 backdrop-blur-md lg:flex-nowrap lg:gap-3 lg:py-0 max-[1023px]:px-2">
      <button
        onClick={exitToLanding}
        className="flex min-w-fit items-baseline gap-2 transition-opacity hover:opacity-80 active:scale-[0.98]"
        aria-label="랜딩 페이지로 돌아가기"
        title="랜딩 페이지로 돌아가기"
      >
        <span className="font-display text-base font-bold tracking-[0.06em] text-text-hi">
          flawless
        </span>
        <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-low max-[1023px]:hidden">
          Combat Replay
        </span>
        <span className="font-mono text-[10px] uppercase text-text-low max-[1180px]:hidden">
          S{activeRun.seed} / {activeRun.scenarioLabel}
        </span>
      </button>

      <LearningPath runId={runId} roundIdx={roundIdx} onSelectRound={setRound} />

      <div className="flex items-center gap-1">
        <button
          onClick={prev}
          aria-label="이전 스텝"
          className="flex h-8 w-8 items-center justify-center text-text-mid transition-colors hover:text-text-hi active:scale-[0.94]"
        >
          <SkipBack size={16} weight="fill" />
        </button>
        <button
          onClick={togglePlay}
          aria-label={playing ? "일시정지" : "재생"}
          className="flex h-8 w-8 items-center justify-center border border-hud-active/45 bg-white/6 text-hud-active transition-colors hover:border-hud-active hover:bg-hud-active/12 active:scale-[0.94]"
        >
          {playing ? <Pause size={16} weight="fill" /> : <Play size={16} weight="fill" />}
        </button>
        <button
          onClick={next}
          aria-label="다음 스텝"
          className="flex h-8 w-8 items-center justify-center text-text-mid transition-colors hover:text-text-hi active:scale-[0.94]"
        >
          <SkipForward size={16} weight="fill" />
        </button>
      </div>

      <div className="flex h-8 items-center border border-white/12 bg-surface-0/70">
        {PLAYBACK_SPEEDS.map((speed) => (
          <button
            key={speed}
            onClick={() => setPlaybackSpeed(speed as PlaybackSpeed)}
            aria-pressed={playbackSpeed === speed}
            className={`h-full px-2 font-mono text-[10px] transition-colors active:scale-[0.96] ${
              playbackSpeed === speed
                ? "bg-hud-active text-surface-0"
                : "text-text-low hover:bg-white/8 hover:text-text-hi"
            }`}
          >
            {speed}x
          </button>
        ))}
      </div>

      <button
        onClick={showResults}
        className="flex h-8 items-center gap-1.5 border border-hud-active/45 bg-hud-active/10 px-2.5 font-display text-[10px] font-semibold uppercase tracking-[0.1em] text-hud-active transition-colors hover:border-hud-active hover:bg-hud-active/18 active:scale-[0.97]"
      >
        <ChartBar size={14} />
        결과보기
      </button>

      <div className="font-mono text-xs text-text-mid max-[1023px]:order-5 max-[1023px]:w-full">
        STEP{" "}
        <span className="text-base text-text-hi">
          {String(step?.step ?? 0).padStart(2, "0")}
        </span>
        <span className="text-text-low"> / {String(total).padStart(2, "0")}</span>
        {step && <span className="ml-3 uppercase text-text-low">{step.phase}</span>}
      </div>

      <div
        className={`hud-clip border px-3 py-1.5 font-display text-xs font-semibold uppercase tracking-[0.08em] ${WINNER_STYLE[side]}`}
        title={round.outcome.reason}
      >
        {side} · {round.outcome.winner_detail}
      </div>

      <button
        onClick={exitToLanding}
        aria-label="랜딩 페이지로 돌아가기"
        title="랜딩 페이지로 돌아가기"
        className="flex h-8 w-8 items-center justify-center border border-transparent text-text-low transition-colors hover:border-hud hover:text-text-hi active:scale-[0.94]"
      >
        <SignOut size={15} />
      </button>
    </header>
  );
}
