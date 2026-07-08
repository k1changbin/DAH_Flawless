import type { ReactNode } from "react";

export type HudAccent = "none" | "cyan" | "red" | "blue";

const STROKE: Record<HudAccent, string> = {
  none: "bg-hud",
  cyan: "bg-hud-active",
  red: "bg-red-ops",
  blue: "bg-blue-def",
};

const TITLE_COLOR: Record<HudAccent, string> = {
  none: "text-text-mid",
  cyan: "text-hud-active",
  red: "text-red-ops",
  blue: "text-blue-def",
};

interface HudFrameProps {
  title?: string;
  accent?: HudAccent;
  className?: string;
  bodyClassName?: string;
  titleRight?: ReactNode;
  children: ReactNode;
}

/** 코너컷 HUD 프레임 (이미지 #8). 1px 스트로크 + 반투명 표면. */
export function HudFrame({
  title,
  accent = "none",
  className = "",
  bodyClassName = "",
  titleRight,
  children,
}: HudFrameProps) {
  return (
    <div className={`hud-clip p-px transition-colors duration-300 ${STROKE[accent]} ${className}`}>
      <div className={`hud-clip flex h-full w-full flex-col bg-surface-1/90 backdrop-blur-md ${bodyClassName}`}>
        {title && (
          <header className="flex shrink-0 items-center justify-between border-b border-hud/60 px-3 py-2">
            <h2
              className={`font-display text-[11px] font-semibold uppercase tracking-[0.08em] transition-colors duration-300 ${TITLE_COLOR[accent]}`}
            >
              {title}
            </h2>
            {titleRight}
          </header>
        )}
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
