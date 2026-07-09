import { motion, AnimatePresence } from "motion/react";
import { CaretLeft, CaretRight, ShieldCheck, Crosshair } from "@phosphor-icons/react";
import { getRound, getStep } from "../data";
import { useReplayStore } from "../store/useReplayStore";
import { useMediaQuery } from "../hooks/useMediaQuery";
import type { DefenseAction, ReplayRound, TimelineStep, ZtaDecision } from "../types/replay";

/** defense_actions는 문자열/객체 혼재 가능 (실데이터 검증됨) */
export function defenseLabel(a: DefenseAction | string): string {
  if (typeof a === "string") return a;
  const target = a.target ? ` ${a.target.split(".").pop()}` : "";
  return `${a.action}${target} [${a.status}]`;
}

/**
 * delta.applied 는 라운드마다 형태가 다르다: mission=평면 숫자({A,B,C}),
 * telemetry=중첩 객체({command_channel:{...}, telemetry_memory_anchor:{...}}).
 * 두 형태 모두 {key,value} 리스트로 평탄화한다 (0 제외).
 */
export function flattenDelta(applied: Record<string, unknown> | null | undefined): { key: string; value: number }[] {
  if (!applied) return [];
  const out: { key: string; value: number }[] = [];
  for (const [k, v] of Object.entries(applied)) {
    if (typeof v === "number") {
      if (v !== 0) out.push({ key: k, value: v });
    } else if (v && typeof v === "object") {
      for (const [ik, iv] of Object.entries(v as Record<string, unknown>)) {
        if (typeof iv === "number" && iv !== 0) out.push({ key: `${k}.${ik}`, value: iv });
      }
    }
  }
  return out;
}

const SPRING = { type: "spring", stiffness: 300, damping: 32 } as const;

const W_RAIL = 56;
const W_NORMAL = 288;
const W_FOCUSED = 416;
const W_COMPACT_RAIL = 48;
const W_COMPACT_NORMAL = 232;
const W_COMPACT_FOCUSED = 352;

function ztaDecisionColor(decision: ZtaDecision): string {
  switch (decision) {
    case "ALLOW":
      return "text-ok border-ok/40";
    case "ALLOW_WITH_MONITOR":
      return "text-hud-active border-hud-active/40";
    case "REVALIDATE":
    case "DEGRADE":
      return "text-warn border-warn/40";
    case "QUARANTINE":
    case "DENY":
      return "text-red-ops border-red-ops/40";
    default:
      return "text-text-mid border-hud";
  }
}

function Gauge({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 w-full bg-surface-2">
      <motion.div
        className={`h-full ${color}`}
        animate={{ width: `${Math.round(Math.min(Math.max(value, 0), 1) * 100)}%` }}
        transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
      />
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-display text-[10px] font-semibold uppercase tracking-[0.1em] text-text-low">
      {children}
    </p>
  );
}

/* ---------- RED 콘텐츠 ---------- */

function RedContent({ step, expanded, round }: { step: TimelineStep | null; expanded: boolean; round: ReplayRound }) {
  const attack = round.attack;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-3">
      <section className="space-y-1.5">
        <Label>Attack Vector</Label>
        <p className="font-mono text-sm font-medium text-red-ops">{attack.name}</p>
        <p className="text-xs text-text-mid">{attack.tactic}</p>
        <span className="inline-block border border-red-dim px-1.5 py-0.5 font-mono text-[10px] uppercase text-red-ops">
          target: {attack.target_domain}
        </span>
      </section>

      {step ? (
        <>
          <section className="space-y-1.5">
            <Label>Current Action</Label>
            <p className="font-mono text-base text-text-hi">{step.red_action}</p>
            <p className="font-mono text-[11px] text-text-low">
              cost {step.budgets.red_last_action_cost.toFixed(4)}
            </p>
          </section>

          <section className="space-y-1.5">
            <Label>Red Budget</Label>
            <div className="flex items-center gap-2">
              <Gauge value={step.budgets.red_budget} color="bg-red-ops" />
              <span className="shrink-0 font-mono text-xs text-text-hi">
                {(step.budgets.red_budget * 100).toFixed(1)}%
              </span>
            </div>
          </section>

          <section className="space-y-1.5">
            <Label>Mutation</Label>
            <div className="flex gap-4 font-mono text-xs text-text-mid">
              <span>
                steps <span className="text-text-hi">{step.budgets.red_mutation_steps}</span>
              </span>
              <span>
                paths <span className="text-text-hi">{step.changed_path_count}</span>
              </span>
            </div>
            <ul className="space-y-0.5">
              {step.changed_paths.slice(0, expanded ? undefined : 3).map((p) => (
                <li key={p} className="truncate font-mono text-[11px] text-text-low">
                  {p}
                </li>
              ))}
              {!expanded && step.changed_paths.length > 3 && (
                <li className="font-mono text-[11px] text-text-low">
                  +{step.changed_paths.length - 3}
                </li>
              )}
            </ul>
          </section>

          <section className="space-y-1.5">
            <Label>Goal</Label>
            <p className="font-mono text-xs text-text-hi">{round.outcome.goal_id}</p>
            <div className="flex gap-4 font-mono text-[11px] text-text-mid">
              <span>
                reward <span className="text-text-hi">{round.outcome.goal_reward.toFixed(2)}</span>
              </span>
              <span className={round.outcome.goal_success ? "text-ok" : "text-text-low"}>
                {round.outcome.goal_success ? "ACHIEVED" : "FAILED"}
              </span>
            </div>
          </section>

          {expanded && (
            <>
              <section className="space-y-1.5">
                <Label>Applied Delta</Label>
                {(() => {
                  const entries = flattenDelta(step.delta?.applied);
                  return entries.length === 0 ? (
                    <p className="font-mono text-[11px] text-text-low">no mutation this step</p>
                  ) : (
                    <ul className="space-y-0.5">
                      {entries.map(({ key, value }) => (
                        <li key={key} className="flex justify-between gap-2 font-mono text-[11px]">
                          <span className="truncate text-text-low">{key}</span>
                          <span
                            className={
                              value > 0 ? "text-red-ops" : value < 0 ? "text-blue-def" : "text-text-mid"
                            }
                          >
                            {value > 0 ? "+" : ""}
                            {value.toFixed(4)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  );
                })()}
              </section>

              <section className="space-y-1.5">
                <Label>Attack Steps</Label>
                <div className="flex gap-1">
                  {round.timeline.map((s) => (
                    <div
                      key={s.step}
                      title={`step ${s.step}: ${s.red_action}`}
                      className={`h-3 flex-1 ${
                        s.red_action === "WAIT"
                          ? "bg-surface-2"
                          : s.red_action === "FINALIZE_ATTACK"
                            ? "bg-red-ops"
                            : "bg-red-dim"
                      }`}
                    />
                  ))}
                </div>
              </section>
            </>
          )}
        </>
      ) : (
        <p className="font-mono text-xs text-text-low">NO STEP DATA</p>
      )}
    </div>
  );
}

/* ---------- BLUE 콘텐츠 (blue_observed만 소비, truth 금지) ---------- */

function BlueContent({ step, expanded, round }: { step: TimelineStep | null; expanded: boolean; round: ReplayRound }) {

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-3">
      {step ? (
        <>
          <section className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Current Action</Label>
              {step.detected && (
                <span className="border border-hud-active/40 px-1.5 py-0.5 font-mono text-[10px] uppercase text-hud-active">
                  detected
                </span>
              )}
            </div>
            <p className="font-mono text-base text-text-hi">{step.blue_action}</p>
          </section>

          <section className="space-y-1.5">
            <Label>Suspicion</Label>
            <div className="flex items-center gap-2">
              <Gauge value={step.suspicion} color="bg-blue-def" />
              <span className="shrink-0 font-mono text-xs text-text-hi">
                {step.suspicion.toFixed(2)}
              </span>
            </div>
          </section>

          <section className="space-y-1.5">
            <Label>ZTA Gate</Label>
            <ul className="space-y-1">
              {step.zta.map((z) => (
                <li
                  key={z.domain}
                  className={`flex items-center justify-between border px-2 py-1 ${ztaDecisionColor(z.decision)}`}
                >
                  <span className="font-mono text-[11px] uppercase">{z.domain}</span>
                  <span className="font-mono text-[11px]">{z.decision}</span>
                  <span className="font-mono text-[10px] text-text-low">
                    {z.trust_score.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section className="space-y-1.5">
            <Label>Defense</Label>
            {step.defense_actions.length > 0 ? (
              <ul className="space-y-0.5">
                {step.defense_actions.map((a, i) => (
                  <li key={i} className="truncate font-mono text-[11px] text-ok">
                    {defenseLabel(a)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="font-mono text-[11px] text-text-low">standby</p>
            )}
          </section>

          <section className="space-y-1.5">
            <Label>Blue Budget</Label>
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="w-14 shrink-0 font-mono text-[10px] text-text-low">compute</span>
                <Gauge value={step.budgets.blue_compute_budget} color="bg-blue-def" />
              </div>
              <div className="flex items-center gap-2">
                <span className="w-14 shrink-0 font-mono text-[10px] text-text-low">power</span>
                <Gauge value={step.budgets.blue_power_budget} color="bg-blue-def" />
              </div>
            </div>
          </section>

          {expanded && (
            <>
              <section className="space-y-1.5">
                <Label>ZTA Reasons</Label>
                <ul className="space-y-0.5">
                  {step.zta.map((z) => (
                    <li key={z.domain} className="font-mono text-[11px] text-text-mid">
                      <span className="uppercase text-text-low">{z.domain}:</span>{" "}
                      {z.reasons.join(", ")}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="space-y-1.5">
                <Label>Round Policy Verdict</Label>
                <ul className="space-y-1">
                  {Object.entries(round.zta_policy.per_domain).map(([domain, v]) => (
                    <li key={domain} className="flex items-center justify-between font-mono text-[11px]">
                      <span className="uppercase text-text-low">{domain}</span>
                      <span className={ztaDecisionColor(v.decision).split(" ")[0]}>{v.decision}</span>
                      <span className={v.correct ? "text-ok" : "text-red-ops"}>
                        {v.correct ? "CORRECT" : "WRONG"}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="font-mono text-[10px] text-text-low">
                  info cost {round.zta_policy.informational_availability_cost.toFixed(4)}
                </p>
              </section>
            </>
          )}
        </>
      ) : (
        <p className="font-mono text-xs text-text-low">NO STEP DATA</p>
      )}
    </div>
  );
}

/* ---------- 패널 셸 ---------- */

export function SidePanel({ side }: { side: "RED" | "BLUE" }) {
  const focus = useReplayStore((s) => s.focus);
  const toggleFocus = useReplayStore((s) => s.toggleFocus);
  const runId = useReplayStore((s) => s.runId);
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const step = getStep(runId, roundIdx, stepIdx);
  const round = getRound(runId, roundIdx);
  const isCompact = useMediaQuery("(max-width: 1439px)");
  const isSheet = useMediaQuery("(max-width: 1023px)");

  const isRed = side === "RED";
  const isFocused = focus === side;
  const isRail = focus !== null && !isFocused;
  const width = isFocused
    ? isCompact
      ? W_COMPACT_FOCUSED
      : W_FOCUSED
    : isRail
      ? isCompact
        ? W_COMPACT_RAIL
        : W_RAIL
      : isCompact
        ? W_COMPACT_NORMAL
        : W_NORMAL;

  const accent = isRed ? "red" : "blue";
  const strokeCls = isFocused ? (isRed ? "bg-red-ops" : "bg-blue-def") : "bg-hud";
  const titleCls = isRed ? "text-red-ops" : "text-blue-def";
  const title = isRed ? "RED OPS" : "BLUE DEF";
  const Icon = isRed ? Crosshair : ShieldCheck;

  if (isSheet) {
    if (!isFocused) {
      return (
        <motion.button
          data-side={side}
          onClick={() => toggleFocus(side)}
          aria-label={`${title} sheet open`}
          className={`fixed top-20 z-30 flex h-32 w-10 flex-col items-center justify-center gap-2 border bg-black/30 shadow-[0_18px_48px_rgba(0,0,0,0.35)] backdrop-blur-md ${
            isRed
              ? "left-2 border-red-dim text-red-ops"
              : "right-2 border-blue-dim text-blue-def"
          }`}
          initial={{ opacity: 0, x: isRed ? -12 : 12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.2 }}
        >
          <Icon size={16} />
          <span
            className="font-display text-[10px] font-semibold uppercase tracking-[0.12em]"
            style={{ writingMode: "vertical-rl" }}
          >
            {isRed ? "RED" : "BLUE"}
          </span>
        </motion.button>
      );
    }

    return (
      <motion.div
        data-side={side}
        className="fixed inset-x-2 bottom-32 top-16 z-40"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 24 }}
        transition={SPRING}
      >
        <div className={`hud-clip h-full p-px ${isRed ? "bg-red-ops" : "bg-blue-def"}`}>
          <div className="hud-clip hud-glass flex h-full flex-col backdrop-blur-md">
            <button
              onClick={() => toggleFocus(side)}
              aria-expanded
              aria-label={`${title} sheet close`}
              className="flex shrink-0 items-center justify-between border-b border-white/12 bg-black/16 px-3 py-2 transition-colors hover:bg-white/8"
            >
              <span className="flex items-center gap-2">
                <Icon size={14} className={titleCls} />
                <span
                  className={`font-display text-[11px] font-semibold uppercase tracking-[0.08em] ${titleCls}`}
                >
                  {title}
                </span>
              </span>
              <span className="font-mono text-[10px] uppercase text-text-low">close</span>
            </button>
            <div className="min-h-0 flex-1">
              {isRed ? (
                <RedContent step={step} expanded round={round} />
              ) : (
                <BlueContent step={step} expanded round={round} />
              )}
            </div>
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      animate={{ width }}
      transition={SPRING}
      className="relative z-10 shrink-0 overflow-hidden"
      data-side={side}
      data-accent={accent}
    >
      <div className={`hud-clip h-full p-px transition-colors duration-300 ${strokeCls}`}>
        <div className="hud-clip hud-glass flex h-full w-full flex-col backdrop-blur-md">
          <AnimatePresence mode="popLayout" initial={false}>
            {isRail ? (
              /* 레일 모드: 클릭하면 이 진영으로 포커스 전환 */
              <motion.button
                key="rail"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                onClick={() => toggleFocus(side)}
                aria-label={`${title} 패널 펼치기`}
                className="flex h-full w-full flex-col items-center gap-3 py-3 transition-colors hover:bg-white/8"
              >
                <Icon size={18} className={titleCls} />
                <span
                  className={`font-display text-[11px] font-semibold uppercase tracking-[0.14em] ${titleCls}`}
                  style={{ writingMode: "vertical-rl" }}
                >
                  {title}
                </span>
                <div className="mt-auto flex h-24 w-1.5 items-end bg-surface-2">
                  <div
                    className={isRed ? "w-full bg-red-ops" : "w-full bg-blue-def"}
                    style={{
                      height: `${Math.round(
                        (isRed ? (step?.budgets.red_budget ?? 0) : (step?.suspicion ?? 0)) * 100,
                      )}%`,
                    }}
                  />
                </div>
              </motion.button>
            ) : (
              <motion.div
                key="full"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="flex h-full flex-col"
              >
                <button
                  onClick={() => toggleFocus(side)}
                  aria-expanded={isFocused}
                  aria-label={`${title} 패널 ${isFocused ? "접기" : "확장"}`}
                  className="flex shrink-0 items-center justify-between border-b border-white/12 bg-black/16 px-3 py-2 transition-colors hover:bg-white/8"
                >
                  <span className="flex items-center gap-2">
                    <Icon size={14} className={titleCls} />
                    <span
                      className={`font-display text-[11px] font-semibold uppercase tracking-[0.08em] ${titleCls}`}
                    >
                      {title}
                    </span>
                  </span>
                  {isRed === isFocused ? (
                    <CaretLeft size={12} className="text-text-low" />
                  ) : (
                    <CaretRight size={12} className="text-text-low" />
                  )}
                </button>
                <div className="min-h-0 flex-1">
                  {isRed ? (
                    <RedContent step={step} expanded={isFocused} round={round} />
                  ) : (
                    <BlueContent step={step} expanded={isFocused} round={round} />
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
