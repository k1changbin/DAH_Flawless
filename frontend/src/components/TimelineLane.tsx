import { getRound } from "../data";
import { useReplayStore } from "../store/useReplayStore";
import type { TimelineStep } from "../types/replay";

function stepEventDots(s: TimelineStep) {
  const dots: { key: string; cls: string; label: string }[] = [];
  if (s.red_action !== "WAIT") {
    dots.push({
      key: "red",
      cls: s.red_action === "FINALIZE_ATTACK" ? "bg-red-ops" : "bg-red-dim",
      label: s.red_action,
    });
  }
  if (s.detected) dots.push({ key: "det", cls: "bg-hud-active", label: "DETECTED" });
  if (s.zta.some((z) => z.restrictive))
    dots.push({ key: "zta", cls: "bg-warn", label: "ZTA RESTRICTED" });
  if (s.defense_actions.length > 0) dots.push({ key: "def", cls: "bg-ok", label: "DEFENSE" });
  return dots;
}

export function TimelineLane() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const setStep = useReplayStore((s) => s.setStep);

  const round = getRound(roundIdx);
  const timeline = round.timeline;
  const highlight = round.highlights.find((h) => h.step === timeline[stepIdx]?.step);

  return (
    <section
      aria-label="전투 타임라인"
      className="relative z-10 shrink-0 border-t border-hud/60 bg-surface-1/80 px-4 pb-3 pt-2 backdrop-blur-md"
    >
      <div className="mb-1.5 flex items-center justify-between">
        <p className="font-display text-[10px] font-semibold uppercase tracking-[0.1em] text-text-low">
          Timeline · {round.title || `Round ${round.round}`}
        </p>
        {highlight && (
          <p className="font-mono text-[11px] text-warn" role="status">
            {highlight.message}
          </p>
        )}
      </div>

      {/* 스텝 마커 */}
      <div className="mb-2 flex gap-1" role="group" aria-label="스텝 마커">
        {timeline.map((s, i) => {
          const active = i === stepIdx;
          return (
            <button
              key={s.step}
              onClick={() => setStep(i)}
              aria-label={`스텝 ${s.step}: ${s.phase}`}
              aria-current={active ? "step" : undefined}
              className={`group flex h-11 flex-1 flex-col items-center justify-between border px-1 py-1 transition-colors ${
                active
                  ? "border-hud-active bg-surface-2"
                  : "border-hud/40 hover:border-hud hover:bg-surface-2/50"
              }`}
            >
              <span
                className={`font-mono text-[10px] leading-none ${
                  active ? "text-hud-active" : "text-text-low group-hover:text-text-mid"
                }`}
              >
                {String(s.step).padStart(2, "0")}
              </span>
              <span className="flex gap-0.5">
                {stepEventDots(s).map((d) => (
                  <span key={d.key} title={d.label} className={`h-1.5 w-1.5 ${d.cls}`} />
                ))}
              </span>
            </button>
          );
        })}
      </div>

      {/* 스크러버 */}
      <input
        type="range"
        className="scrubber"
        min={0}
        max={Math.max(timeline.length - 1, 0)}
        value={stepIdx}
        onChange={(e) => setStep(Number(e.target.value))}
        aria-label="스텝 스크러버"
      />
    </section>
  );
}
