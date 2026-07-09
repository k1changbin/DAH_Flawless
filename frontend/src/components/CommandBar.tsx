import { Pause, Play, SignOut, SkipBack, SkipForward } from "@phosphor-icons/react";
import { replay, getRound, getStep } from "../data";
import { useReplayStore } from "../store/useReplayStore";
import type { WinnerSide } from "../types/replay";

const WINNER_STYLE: Record<WinnerSide, string> = {
  BLUE: "border-blue-def text-blue-def",
  RED: "border-red-ops text-red-ops",
  DRAW: "border-hud text-text-mid",
};

export function CommandBar() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const playing = useReplayStore((s) => s.playing);
  const setRound = useReplayStore((s) => s.setRound);
  const togglePlay = useReplayStore((s) => s.togglePlay);
  const next = useReplayStore((s) => s.next);
  const prev = useReplayStore((s) => s.prev);
  const exitToLanding = useReplayStore((s) => s.exitToLanding);

  const round = getRound(roundIdx);
  const step = getStep(roundIdx, stepIdx);
  const total = round.timeline.length;
  const side = round.outcome.winner_side;

  return (
    <header className="dashboard-bar relative z-10 flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b border-white/14 px-4 py-2 backdrop-blur-md lg:flex-nowrap lg:gap-4 lg:py-0 max-[1023px]:px-2">
      <button
        onClick={exitToLanding}
        className="flex min-w-fit items-baseline gap-2 transition-opacity hover:opacity-80 active:scale-[0.98]"
        aria-label="랜딩 페이지로 돌아가기"
        title="랜딩 페이지로 돌아가기"
      >
        <span className="font-display text-base font-bold tracking-[0.06em] text-text-hi">
          DAH FLAWLESS
        </span>
        <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-low max-[1023px]:hidden">
          Combat Replay
        </span>
      </button>

      <nav aria-label="라운드 선택" className="flex max-w-[42vw] items-center gap-1 overflow-x-auto lg:max-w-none">
        {replay.rounds.map((r, i) => (
          <button
            key={r.round}
            onClick={() => setRound(i)}
            aria-pressed={i === roundIdx}
            className={`h-8 min-w-9 px-2 font-mono text-xs transition-colors ${
              i === roundIdx
                ? "border border-hud-active bg-hud-active/14 text-hud-active shadow-[0_0_18px_rgba(95,212,245,0.16)]"
                : "border border-transparent text-text-mid hover:border-white/18 hover:bg-white/8 hover:text-text-hi"
            }`}
          >
            R{r.round}
          </button>
        ))}
      </nav>

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

      <div className="font-mono text-xs text-text-mid max-[1023px]:order-5 max-[1023px]:w-full">
        STEP{" "}
        <span className="text-base text-text-hi">
          {String(step?.step ?? 0).padStart(2, "0")}
        </span>
        <span className="text-text-low"> / {String(total).padStart(2, "0")}</span>
        {step && <span className="ml-3 uppercase text-text-low">{step.phase}</span>}
      </div>

      <div className="flex-1" />

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
