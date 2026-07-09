import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  Broadcast,
  Crosshair,
  LockKey,
  ShieldCheck,
  Waveform,
} from "@phosphor-icons/react";
import { replay } from "../data";
import { useReplayStore } from "../store/useReplayStore";

const EASE = [0.23, 1, 0.32, 1] as const;

const METRICS = [
  { label: "ROUNDS", value: replay.rounds.length.toString(), tone: "text-hud-active" },
  { label: "SEED", value: "42", tone: "text-warn" },
  { label: "ZTA", value: "ON", tone: "text-ok" },
];

const SIDE_COPY = {
  RED: {
    icon: Crosshair,
    title: "RED OFFENSE",
    body: "송출 텔레메트리는 관측만 가능하고, 수신 흐름은 기억 기반 혼동 자원으로 축적됩니다.",
    tone: "border-red-ops/55 bg-red-ops/10 text-red-ops",
    bar: "bg-red-ops",
    score: "FDI",
  },
  BLUE: {
    icon: ShieldCheck,
    title: "BLUE DEFENSE",
    body: "ZTA 정책과 내부 관측 anchor를 기준으로 명령 신뢰도와 복구 경로를 판별합니다.",
    tone: "border-blue-def/55 bg-blue-def/10 text-blue-def",
    bar: "bg-blue-def",
    score: "ZTA",
  },
} as const;

const SIGNALS = [
  { label: "TX BATTERY", value: "READ ONLY", cls: "text-ok" },
  { label: "RX COMMAND", value: "MEMORY", cls: "text-warn" },
  { label: "MOTOR RPM", value: "LOCKED", cls: "text-hud-active" },
];

type Side = keyof typeof SIDE_COPY;

export function Landing() {
  const enter = useReplayStore((s) => s.enter);
  const reduce = useReducedMotion();
  const [activeSide, setActiveSide] = useState<Side>("RED");

  const introMotion = reduce
    ? {}
    : {
        initial: { opacity: 0, y: 18 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.55, ease: EASE },
      };

  return (
    <motion.main
      className="landing-shell relative z-10 h-full overflow-y-auto px-4 py-4 sm:px-8 sm:py-6"
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, scale: 1.015 }}
      transition={{ duration: 0.42, ease: EASE }}
    >
      <div className="landing-backdrop" aria-hidden />

      <div className="mx-auto flex min-h-[calc(100dvh-2rem)] w-full max-w-[1220px] items-center sm:min-h-[calc(100dvh-3rem)]">
        <motion.section
          {...introMotion}
          className="landing-window relative grid w-full overflow-hidden border border-white/20 bg-white/[0.075] text-text-hi shadow-2xl backdrop-blur-2xl"
          aria-label="DAH FLAWLESS 시작 화면"
        >
          <header className="relative z-10 flex min-h-12 items-center justify-between gap-4 border-b border-white/15 bg-black/20 px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex gap-1.5" aria-hidden>
                <span className="h-2.5 w-2.5 rounded-full bg-red-ops" />
                <span className="h-2.5 w-2.5 rounded-full bg-warn" />
                <span className="h-2.5 w-2.5 rounded-full bg-ok" />
              </div>
              <span className="truncate font-display text-xs font-semibold uppercase text-text-mid">
                Combat replay console
              </span>
            </div>
            <div className="hidden items-center gap-2 font-mono text-[10px] text-text-low sm:flex">
              <span className="h-1.5 w-1.5 rounded-full bg-hud-active shadow-[0_0_12px_rgba(95,212,245,0.85)]" />
              simulation ready
            </div>
          </header>

          <div className="relative z-10 grid min-h-[620px] gap-0 lg:grid-cols-[0.86fr_1.14fr] max-[760px]:min-h-0">
            <section className="flex min-w-0 flex-col justify-between gap-8 border-b border-white/15 p-5 sm:p-7 lg:border-b-0 lg:border-r lg:border-white/15 lg:p-9">
              <div>
                <p className="mb-4 inline-flex items-center gap-2 border border-white/15 bg-white/10 px-2.5 py-1 font-display text-[11px] font-semibold uppercase text-hud-active backdrop-blur-md">
                  <Broadcast size={15} />
                  Drone autonomous replay
                </p>
                <h1 className="max-w-[8ch] font-display text-5xl font-bold leading-none text-white sm:text-6xl">
                  DAH FLAWLESS
                </h1>
                <p className="mt-5 max-w-md text-base leading-7 text-text-hi/86">
                  레드의 관측 흐름과 블루의 신뢰 판별을 하나의 전장 콘솔에서 재생합니다.
                  송출값은 관측 전용 신호로 잠그고, 수신값은 기억 기반 혼동 자원으로 추적합니다.
                </p>
              </div>

              <div className="space-y-5">
                <div className="grid grid-cols-3 gap-2">
                  {METRICS.map((m) => (
                    <div key={m.label} className="border border-white/12 bg-black/24 px-3 py-3 backdrop-blur-md">
                      <p className="font-mono text-[10px] uppercase text-text-low">{m.label}</p>
                      <p className={`mt-1 font-display text-xl font-bold ${m.tone}`}>{m.value}</p>
                    </div>
                  ))}
                </div>

                <button
                  onClick={enter}
                  className="group flex w-full items-center justify-between border border-hud-active/70 bg-hud-active px-4 py-3.5 text-left font-display text-sm font-bold uppercase text-surface-0 shadow-[0_0_30px_rgba(95,212,245,0.22)] transition-transform hover:-translate-y-0.5 active:translate-y-0"
                >
                  <span>시뮬레이션 진입</span>
                  <ArrowRight
                    size={18}
                    className="transition-transform group-hover:translate-x-1"
                    aria-hidden
                  />
                </button>
              </div>
            </section>

            <section className="relative min-h-[520px] overflow-hidden p-3 sm:p-4 lg:min-h-0" aria-label="전장 미리보기">
              <div className="landing-visual relative h-full min-h-[500px] overflow-hidden border border-white/15 bg-surface-0/60">
                <div className="landing-wireframe" aria-hidden />

                <div className="relative z-10 grid h-full grid-rows-[1fr_auto]">
                  <div className="grid gap-3 p-4 sm:grid-cols-[1fr_230px] sm:p-5">
                    <div className="flex min-h-[260px] flex-col justify-between">
                      <div className="max-w-xs">
                        <p className="font-display text-[11px] font-semibold uppercase text-text-low">
                          Mission telemetry split
                        </p>
                        <p className="mt-2 text-2xl font-semibold leading-tight text-white">
                          월드값 기반 송출/수신 흐름을
                          <br />
                          분리해서 보여줍니다.
                        </p>
                      </div>

                      <div className="grid max-w-xl gap-2 sm:grid-cols-3">
                        {SIGNALS.map((signal) => (
                          <div key={signal.label} className="border border-white/12 bg-black/38 p-3 backdrop-blur-md">
                            <p className="font-mono text-[10px] text-text-low">{signal.label}</p>
                            <p className={`mt-2 font-display text-sm font-semibold ${signal.cls}`}>{signal.value}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="grid content-start gap-2">
                      {(["RED", "BLUE"] as Side[]).map((side) => {
                        const item = SIDE_COPY[side];
                        const Icon = item.icon;
                        const active = activeSide === side;

                        return (
                          <button
                            key={side}
                            onMouseEnter={() => setActiveSide(side)}
                            onFocus={() => setActiveSide(side)}
                            onClick={() => setActiveSide(side)}
                            className={`border p-3 text-left backdrop-blur-md transition-colors ${
                              active
                                ? item.tone
                                : "border-white/12 bg-black/30 text-text-mid hover:border-white/24"
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="flex items-center gap-2 font-display text-xs font-semibold">
                                <Icon size={15} />
                                {item.title}
                              </span>
                              <span className="font-mono text-[10px]">{item.score}</span>
                            </div>
                            <p className="mt-3 text-xs leading-5 text-text-hi/80">{item.body}</p>
                            <div className="mt-3 h-1 bg-white/12">
                              <div className={`h-full ${item.bar}`} style={{ width: active ? "76%" : "42%" }} />
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid border-t border-white/15 bg-black/42 backdrop-blur-md sm:grid-cols-3">
                    <div className="flex items-center gap-3 border-b border-white/10 p-4 sm:border-b-0 sm:border-r">
                      <Broadcast size={18} className="shrink-0 text-ok" />
                      <div>
                        <p className="font-mono text-[10px] text-text-low">TX STREAM</p>
                        <p className="text-sm text-text-hi">read-only signal</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 border-b border-white/10 p-4 sm:border-b-0 sm:border-r">
                      <Waveform size={18} className="shrink-0 text-warn" />
                      <div>
                        <p className="font-mono text-[10px] text-text-low">RX MEMORY</p>
                        <p className="text-sm text-text-hi">confusion resource</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 p-4">
                      <LockKey size={18} className="shrink-0 text-hud-active" />
                      <div>
                        <p className="font-mono text-[10px] text-text-low">RED ACCESS</p>
                        <p className="text-sm text-text-hi">observe only</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </motion.section>
      </div>
    </motion.main>
  );
}
