import { Suspense, lazy } from "react";
import { HudFrame } from "./HudFrame";
import { getRound } from "../data";
import { useReplayStore } from "../store/useReplayStore";

const BattlefieldScene = lazy(() =>
  import("./scene/BattlefieldScene").then((m) => ({ default: m.BattlefieldScene })),
);

const LEGEND = [
  { cls: "bg-red-ops", label: "attack flow" },
  { cls: "bg-warn", label: "zta restricted" },
  { cls: "bg-hud-active", label: "detected" },
] as const;

export function CenterScene() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const round = getRound(roundIdx);

  return (
    <HudFrame
      title="Tactical Scene"
      className="h-full"
      titleRight={
        <span className="font-mono text-[10px] text-text-low">
          {round.attack.target_domain} vector
        </span>
      }
    >
      <div className="relative h-full">
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center">
              <p className="animate-pulse font-display text-xs font-semibold uppercase tracking-[0.2em] text-text-low">
                Scene Loading
              </p>
            </div>
          }
        >
          <BattlefieldScene />
        </Suspense>

        {/* 범례 오버레이 */}
        <div className="pointer-events-none absolute bottom-2 left-3 flex gap-4">
          {LEGEND.map((l) => (
            <span key={l.label} className="flex items-center gap-1.5 font-mono text-[10px] text-text-low">
              <span className={`h-1.5 w-1.5 ${l.cls}`} />
              {l.label}
            </span>
          ))}
        </div>
      </div>
    </HudFrame>
  );
}
