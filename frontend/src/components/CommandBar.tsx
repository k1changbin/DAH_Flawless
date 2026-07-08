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
    <header className="relative z-10 flex h-14 shrink-0 items-center gap-4 border-b border-hud/60 bg-surface-1/80 px-4 backdrop-blur-md">
      {/* 워드마크 */}
      <div className="flex items-baseline gap-2">
        <span className="font-display text-base font-bold tracking-[0.06em] text-text-hi">
          DAH FLAWLESS
        </span>
        <span className="font-display text-[10px] font-semibold uppercase tracking-[0.14em] text-text-low">
          Combat Replay
        </span>
      </div>

      {/* 라운드 선택 */}
      <nav aria-label="라운드 선택" className="flex items-center gap-1">
        {replay.rounds.map((r, i) => (
          <button
            key={r.round}
            onClick={() => setRound(i)}
            aria-pressed={i === roundIdx}
            className={`h-8 min-w-9 px-2 font-mono text-xs transition-colors ${
              i === roundIdx
                ? "border border-hud-active bg-surface-2 text-hud-active"
                : "border border-transparent text-text-mid hover:border-hud hover:text-text-hi"
            }`}
          >
            R{r.round}
          </button>
        ))}
      </nav>

      {/* 재생 컨트롤 */}
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
          className="flex h-8 w-8 items-center justify-center border border-hud text-hud-active transition-colors hover:border-hud-active active:scale-[0.94]"
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

      {/* 타임코드 */}
      <div className="font-mono text-xs text-text-mid">
        STEP{" "}
        <span className="text-base text-text-hi">
          {String((step?.step ?? 0)).padStart(2, "0")}
        </span>
        <span className="text-text-low"> / {String(total).padStart(2, "0")}</span>
        {step && <span className="ml-3 uppercase text-text-low">{step.phase}</span>}
      </div>

      <div className="flex-1" />

      {/* 승패 배지 */}
      <div
        className={`hud-clip border px-3 py-1.5 font-display text-xs font-semibold uppercase tracking-[0.08em] ${WINNER_STYLE[side]}`}
        title={round.outcome.reason}
      >
        {side} · {round.outcome.winner_detail}
      </div>

      {/* 런처로 나가기 */}
      <button
        onClick={exitToLanding}
        aria-label="런처로 나가기"
        title="런처로 나가기"
        className="flex h-8 w-8 items-center justify-center border border-transparent text-text-low transition-colors hover:border-hud hover:text-text-hi active:scale-[0.94]"
      >
        <SignOut size={15} />
      </button>
    </header>
  );
}
