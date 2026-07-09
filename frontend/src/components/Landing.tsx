import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  Broadcast,
  Crosshair,
  LockKey,
  ShieldCheck,
  Waveform,
} from "@phosphor-icons/react";
import { getRun, SCENARIO_OPTIONS, SEED_OPTIONS, type ReplayScenarioId } from "../data";
import { buildLearningProfile, MAX_LEARNING_ROUNDS } from "../learning";
import { useReplayStore } from "../store/useReplayStore";

const EASE = [0.23, 1, 0.32, 1] as const;

const SIDE_COPY = {
  RED: {
    icon: Crosshair,
    title: "RED OFFENSE",
    tone: "border-red-ops/55 bg-red-ops/10 text-red-ops",
    bar: "bg-red-ops",
    score: "FDI",
  },
  BLUE: {
    icon: ShieldCheck,
    title: "BLUE DEFENSE",
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
  const runId = useReplayStore((s) => s.runId);
  const seed = useReplayStore((s) => s.seed);
  const scenario = useReplayStore((s) => s.scenario);
  const roundLimit = useReplayStore((s) => s.roundLimit);
  const setRunSelection = useReplayStore((s) => s.setRunSelection);
  const setRoundLimit = useReplayStore((s) => s.setRoundLimit);
  const reduce = useReducedMotion();
  const [activeSide, setActiveSide] = useState<Side>("RED");
  const [roundLimitText, setRoundLimitText] = useState(String(roundLimit));
  const activeRun = getRun(runId);
  const requestedLimit = Math.min(Math.max(roundLimit, 1), MAX_LEARNING_ROUNDS);
  const learning = useMemo(() => buildLearningProfile(activeRun.replay, 0, roundLimit), [activeRun, roundLimit]);
  const shiftRound =
    learning.shiftIndex === null ? null : activeRun.replay.rounds[learning.shiftIndex];
  const metrics = [
    { label: "REQUESTED", value: requestedLimit.toString(), tone: "text-hud-active" },
    { label: "LOADED", value: activeRun.replay.rounds.length.toString(), tone: "text-ok" },
    { label: "SEED", value: String(activeRun.seed), tone: "text-warn" },
  ];

  useEffect(() => {
    setRoundLimitText(String(roundLimit));
  }, [roundLimit]);

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
          aria-label="flawless 시작 화면"
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
                <h1 className="font-display text-5xl font-bold lowercase leading-none text-white sm:text-6xl">
                  flawless
                </h1>
                <p className="mt-4 max-w-lg text-sm leading-6 text-text-hi/88">
                  Seed, Scenario, Rounds를 정하면 최대 2000R 안에서 Red의 관측 신뢰 교란과
                  Blue의 anchor/ZTA 대응이 라운드별 승패, 역전 구간, 정책 분포로 어떻게 바뀌는지
                  압축해서 보여줍니다.
                </p>
              </div>

              <div className="grid gap-2 border border-white/12 bg-black/24 p-3 text-xs leading-5 text-text-mid backdrop-blur-md">
                <p className="font-display text-[10px] font-semibold uppercase tracking-[0.12em] text-hud-active">
                  How to read this replay
                </p>
                <p>
                  같은 Seed는 같은 흐름을 재현하고, Scenario는 SATCOM 지연이나 텔레메트리 충돌 같은
                  출발 조건을 바꿉니다. Rounds에는 보고 싶은 상한을 입력한 뒤 진입하고, 상단 배속과
                  결과보기로 긴 학습 흐름을 빠르게 훑습니다.
                </p>
              </div>

              <div className="space-y-5">
                <div className="grid grid-cols-3 gap-2">
                  {metrics.map((m) => (
                    <div key={m.label} className="border border-white/12 bg-black/24 px-3 py-3 backdrop-blur-md">
                      <p className="font-mono text-[10px] uppercase text-text-low">{m.label}</p>
                      <p className={`mt-1 font-display text-xl font-bold ${m.tone}`}>{m.value}</p>
                    </div>
                  ))}
                </div>

                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="grid gap-1 border border-white/12 bg-black/24 px-3 py-2 backdrop-blur-md">
                    <span className="font-mono text-[10px] uppercase text-text-low">Seed</span>
                    <select
                      value={seed}
                      onChange={(e) => setRunSelection(Number(e.target.value), scenario)}
                      className="h-9 border border-white/12 bg-surface-0 px-2 font-display text-sm font-semibold uppercase text-text-hi outline-none transition-colors hover:border-hud-active focus:border-hud-active"
                    >
                      {SEED_OPTIONS.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="grid gap-1 border border-white/12 bg-black/24 px-3 py-2 backdrop-blur-md">
                    <span className="font-mono text-[10px] uppercase text-text-low">Scenario</span>
                    <select
                      value={scenario}
                      onChange={(e) => setRunSelection(seed, e.target.value as ReplayScenarioId)}
                      className="h-9 border border-white/12 bg-surface-0 px-2 font-display text-sm font-semibold uppercase text-text-hi outline-none transition-colors hover:border-hud-active focus:border-hud-active"
                    >
                      {SCENARIO_OPTIONS.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                    <p className="min-h-8 text-[11px] leading-4 text-text-mid">{activeRun.scenarioDescription}</p>
                  </label>

                  <label className="grid gap-1 border border-white/12 bg-black/24 px-3 py-2 backdrop-blur-md sm:col-span-2">
                    <span className="font-mono text-[10px] uppercase text-text-low">
                      Requested rounds · max {MAX_LEARNING_ROUNDS} · loaded detail {activeRun.replay.rounds.length}
                    </span>
                    <input
                      value={roundLimitText}
                      onChange={(event) => setRoundLimitText(event.target.value)}
                      onBlur={() => {
                        const next = Number(roundLimitText);
                        if (Number.isFinite(next)) setRoundLimit(next);
                        else setRoundLimitText(String(roundLimit));
                      }}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          const next = Number(roundLimitText);
                          if (Number.isFinite(next)) setRoundLimit(next);
                          event.currentTarget.blur();
                        }
                      }}
                      inputMode="numeric"
                      aria-label="표시 라운드 수"
                      className="h-9 border border-white/12 bg-surface-0 px-2 font-display text-sm font-semibold uppercase text-text-hi outline-none transition-colors hover:border-hud-active focus:border-hud-active"
                    />
                  </label>
                </div>

                <div className="border border-white/12 bg-black/24 p-3 backdrop-blur-md">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div>
                      <p className="font-display text-[10px] font-semibold uppercase tracking-[0.12em] text-text-low">
                        Learning arc
                      </p>
                      <p className="font-mono text-[10px] text-text-mid">
                        {learning.markerCount} snapshots · {learning.visibleRounds} detail / {requestedLimit} requested
                      </p>
                    </div>
                    <div className="text-right font-mono text-[10px] text-text-low">
                      <p>
                        BLUE <span className="text-blue-def">{learning.winnerCounts.BLUE}</span>
                      </p>
                      <p>
                        RED <span className="text-red-ops">{learning.winnerCounts.RED}</span>
                      </p>
                    </div>
                  </div>
                  <div className="mb-2 flex h-5 items-end gap-px overflow-hidden border border-white/10 bg-surface-0 px-1 py-1">
                    {learning.bins.map((bin) => (
                      <div
                        key={`${bin.fromRound}-${bin.toRound}`}
                        className={
                          bin.dominant === "BLUE"
                            ? "min-w-0 flex-1 bg-blue-def"
                            : bin.dominant === "RED"
                              ? "min-w-0 flex-1 bg-red-ops"
                              : "min-w-0 flex-1 bg-text-low"
                        }
                        style={{
                          height: `${35 + Math.abs(bin.score) * 65}%`,
                          opacity: 0.24 + Math.max(bin.blueRate, bin.redRate, bin.drawRate) * 0.58,
                        }}
                      />
                    ))}
                  </div>
                  <div className="flex items-center justify-between gap-3 font-mono text-[10px] text-text-low">
                    <span>
                      {learning.firstBlueIndex === null
                        ? "first BLUE pending"
                        : `first BLUE R${activeRun.replay.rounds[learning.firstBlueIndex].round}`}
                    </span>
                    <span className="text-right">
                      {shiftRound ? `shift R${shiftRound.round} · ${shiftRound.attack.target_domain}` : "shift pending"}
                    </span>
                  </div>
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
                      <div className="max-w-[24rem]">
                        <p className="font-display text-[11px] font-semibold uppercase text-text-low">
                          Observe-integrity replay
                        </p>
                        <p className="mt-2 text-[1.45rem] font-semibold leading-snug text-white [word-break:keep-all] sm:text-2xl">
                          <span className="block">관측 신뢰가 흔들릴 때</span>
                          <span className="block">판단 흐름이 어떻게 바뀌는지</span>
                          <span className="block">라운드로 압축합니다.</span>
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
                            <p className="mt-3 text-xs leading-5 text-text-hi/80">
                              {side === "RED"
                                ? "외부 관측면에서 신뢰를 흔드는 공격 선택, 변조 경로, 라운드별 성과를 추적합니다."
                                : "내부 anchor와 ZTA 정책을 기준으로 관측값을 제한, 격리, 복구한 판단 흐름을 압축합니다."}
                            </p>
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
