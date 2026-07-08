import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Crosshair, ShieldCheck } from "@phosphor-icons/react";
import { replay } from "../data";
import { useReplayStore } from "../store/useReplayStore";

const SPRING = { type: "spring", stiffness: 220, damping: 30 } as const;

const RED_ITEMS = ["TIME_DESYNC_REPLAY", "TELEMETRY_FDI", "PRIORITY_POISONING"];
const BLUE_ITEMS = ["ZTA POLICY GATE", "INTERNAL OBSERVE ANCHOR", "TRUSTED RESTORE"];

/**
 * 게임 런처식 랜딩 (레퍼런스: 좌우 스플릿 히어로).
 * 좌 = RED 공격, 우 = BLUE 방어. 호버로 진영이 밀고 당기고, CTA로 대시보드 진입.
 */
export function Landing() {
  const enter = useReplayStore((s) => s.enter);
  const reduce = useReducedMotion();
  const [side, setSide] = useState<"RED" | "BLUE" | null>(null);

  const half = (mine: "RED" | "BLUE") =>
    side === null ? 1 : side === mine ? 1.45 : 0.7;

  return (
    <motion.div
      className="relative z-10 flex h-full overflow-hidden"
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 1.03 }}
      transition={{ duration: 0.45, ease: [0.23, 1, 0.32, 1] }}
    >
      {/* RED 공격 진영 */}
      <motion.section
        onMouseEnter={() => setSide("RED")}
        onMouseLeave={() => setSide(null)}
        onClick={() => setSide("RED")}
        animate={{ flexGrow: half("RED") }}
        transition={SPRING}
        className="relative min-w-0 basis-0 cursor-pointer overflow-hidden border-r border-hud/60"
        style={{
          background:
            "radial-gradient(ellipse 90% 80% at 20% 75%, rgba(255, 93, 69, 0.14), transparent 65%)",
        }}
        aria-label="RED 공격 진영"
      >
        <motion.div
          initial={reduce ? false : { x: -40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ delay: 0.15, duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
          className="absolute bottom-16 left-10"
        >
          <p className="mb-2 flex items-center gap-2 font-display text-[11px] font-semibold uppercase tracking-[0.2em] text-red-ops">
            <Crosshair size={14} /> 공격 진영
          </p>
          <h2 className="font-display text-7xl font-bold leading-none tracking-tight text-text-hi">
            RED
          </h2>
          <p className="mt-1 font-display text-2xl font-semibold uppercase tracking-[0.08em] text-red-ops">
            Offense
          </p>
          <ul className="mt-5 space-y-1">
            {RED_ITEMS.map((it) => (
              <li key={it} className="font-mono text-[11px] text-text-mid">
                {it}
              </li>
            ))}
          </ul>
        </motion.div>
        <motion.div
          className="pointer-events-none absolute inset-0 bg-surface-0"
          animate={{ opacity: side === "BLUE" ? 0.55 : 0 }}
          transition={{ duration: 0.3 }}
        />
      </motion.section>

      {/* BLUE 방어 진영 */}
      <motion.section
        onMouseEnter={() => setSide("BLUE")}
        onMouseLeave={() => setSide(null)}
        onClick={() => setSide("BLUE")}
        animate={{ flexGrow: half("BLUE") }}
        transition={SPRING}
        className="relative min-w-0 basis-0 cursor-pointer overflow-hidden"
        style={{
          background:
            "radial-gradient(ellipse 90% 80% at 80% 75%, rgba(79, 163, 255, 0.14), transparent 65%)",
        }}
        aria-label="BLUE 방어 진영"
      >
        <motion.div
          initial={reduce ? false : { x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ delay: 0.15, duration: 0.5, ease: [0.23, 1, 0.32, 1] }}
          className="absolute bottom-16 right-10 text-right"
        >
          <p className="mb-2 flex items-center justify-end gap-2 font-display text-[11px] font-semibold uppercase tracking-[0.2em] text-blue-def">
            방어 진영 <ShieldCheck size={14} />
          </p>
          <h2 className="font-display text-7xl font-bold leading-none tracking-tight text-text-hi">
            BLUE
          </h2>
          <p className="mt-1 font-display text-2xl font-semibold uppercase tracking-[0.08em] text-blue-def">
            Defense
          </p>
          <ul className="mt-5 space-y-1">
            {BLUE_ITEMS.map((it) => (
              <li key={it} className="font-mono text-[11px] text-text-mid">
                {it}
              </li>
            ))}
          </ul>
        </motion.div>
        <motion.div
          className="pointer-events-none absolute inset-0 bg-surface-0"
          animate={{ opacity: side === "RED" ? 0.55 : 0 }}
          transition={{ duration: 0.3 }}
        />
      </motion.section>

      {/* 중앙 오버레이: 타이틀 + 진입 CTA */}
      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-between py-16">
        <motion.header
          initial={reduce ? false : { y: -16, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.4, ease: [0.23, 1, 0.32, 1] }}
          className="text-center"
        >
          <h1 className="font-display text-2xl font-bold tracking-[0.1em] text-text-hi">
            DAH FLAWLESS
          </h1>
          <p className="mt-2 text-sm text-text-mid">
            Red 공격과 Blue 방어가 벌이는 자율 교전의 전투 리플레이
          </p>
        </motion.header>

        <motion.div
          initial={reduce ? false : { scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ delay: 0.7, type: "spring", stiffness: 260, damping: 20 }}
          className="pointer-events-auto flex flex-col items-center gap-3"
        >
          <button
            onClick={enter}
            className="hud-clip border border-hud-active bg-surface-1/80 px-10 py-3.5 font-display text-sm font-bold uppercase tracking-[0.16em] text-hud-active backdrop-blur-md transition-colors hover:bg-surface-2 active:scale-[0.98]"
          >
            시뮬레이션 진입
          </button>
          <p className="font-mono text-[10px] text-text-low">
            {replay.rounds.length} rounds / seed 42 / zta gate active
          </p>
        </motion.div>
      </div>
    </motion.div>
  );
}
