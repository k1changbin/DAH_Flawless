import { useMemo } from "react";
import { HudFrame } from "./HudFrame";
import { defenseLabel } from "./SidePanel";
import { getRound, getStep } from "../data";
import { useReplayStore } from "../store/useReplayStore";
import type { ZtaDecision, ZtaDomain } from "../types/replay";

const DOMAINS: ZtaDomain[] = ["command", "telemetry", "mission"];

function decisionBg(decision: ZtaDecision): string {
  switch (decision) {
    case "ALLOW":
      return "bg-ok/70";
    case "ALLOW_WITH_MONITOR":
      return "bg-hud-active/70";
    case "REVALIDATE":
    case "DEGRADE":
      return "bg-warn/80";
    case "QUARANTINE":
    case "DENY":
      return "bg-red-ops/80";
    default:
      return "bg-surface-2";
  }
}

/* ---------- 1. Suspicion 스파크라인 ---------- */

function SuspicionSparkline() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const round = getRound(roundIdx);
  const step = getStep(roundIdx, stepIdx);

  const W = 208;
  const H = 44;
  const points = useMemo(() => {
    const t = round.timeline;
    if (t.length < 2) return "";
    return t
      .map((s, i) => `${(i / (t.length - 1)) * W},${H - 4 - s.suspicion * (H - 8)}`)
      .join(" ");
  }, [round]);

  const cx = round.timeline.length > 1 ? (stepIdx / (round.timeline.length - 1)) * W : 0;
  const cy = H - 4 - (step?.suspicion ?? 0) * (H - 8);

  return (
    <HudFrame
      title="Suspicion"
      accent="blue"
      className="w-60"
      titleRight={
        <span className="font-mono text-[10px] text-text-hi">{(step?.suspicion ?? 0).toFixed(2)}</span>
      }
    >
      <div className="p-2">
        <svg width={W} height={H} className="block">
          <line x1={0} y1={H - 4} x2={W} y2={H - 4} stroke="var(--color-hud)" strokeWidth={1} />
          <polyline points={points} fill="none" stroke="var(--color-blue-def)" strokeWidth={1.5} />
          <circle cx={cx} cy={cy} r={3} fill="var(--color-hud-active)" />
        </svg>
      </div>
    </HudFrame>
  );
}

/* ---------- 2. ZTA 정책 타임라인 ---------- */

function ZtaPolicyLane() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const setStep = useReplayStore((s) => s.setStep);
  const round = getRound(roundIdx);

  return (
    <HudFrame title="ZTA Policy" accent="cyan" className="w-60">
      <div className="space-y-1 p-2">
        {DOMAINS.map((domain) => (
          <div key={domain} className="flex items-center gap-1.5">
            <span className="w-8 shrink-0 font-mono text-[9px] uppercase text-text-low">
              {domain.slice(0, 3)}
            </span>
            <div className="flex flex-1 gap-0.5">
              {round.timeline.map((s, i) => {
                const z = s.zta.find((d) => d.domain === domain);
                return (
                  <button
                    key={s.step}
                    onClick={() => setStep(i)}
                    aria-label={`스텝 ${s.step} ${domain}: ${z?.decision ?? "없음"}`}
                    title={`${s.step}: ${z?.decision ?? ""}`}
                    className={`h-2.5 flex-1 transition-transform hover:scale-y-125 ${
                      z ? decisionBg(z.decision) : "bg-surface-2"
                    } ${z?.decision === "DENY" ? "deny-pop" : ""} ${
                      i === stepIdx ? "outline outline-1 outline-hud-active" : ""
                    }`}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </HudFrame>
  );
}

/* ---------- 3. 텔레메트리 피드 ---------- */

function TelemetryFeed() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const step = getStep(roundIdx, stepIdx);

  if (!step) return null;

  const rows = [
    ...step.zta.map((z) => ({
      k: `trust.${z.domain}`,
      v: z.trust_score.toFixed(3),
      warn: z.restrictive,
    })),
    { k: "blue.compute", v: step.budgets.blue_compute_budget.toFixed(3), warn: false },
    { k: "blue.power", v: step.budgets.blue_power_budget.toFixed(3), warn: false },
  ];

  return (
    <HudFrame title="Telemetry" className="w-56">
      <ul className="space-y-0.5 p-2">
        {rows.map((r) => (
          <li key={r.k} className="flex justify-between font-mono text-[10px]">
            <span className="text-text-low">{r.k}</span>
            <span className={r.warn ? "text-warn" : "text-text-mid"}>{r.v}</span>
          </li>
        ))}
      </ul>
    </HudFrame>
  );
}

/* ---------- 4. 이벤트 로그 (최신이 위) ---------- */

interface LogEvent {
  step: number;
  text: string;
  cls: string;
}

function EventLog() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const round = getRound(roundIdx);
  const step = getStep(roundIdx, stepIdx);
  const attacking = step !== null && step.red_action !== "WAIT" && step.red_action !== "ABORT";
  const deny = Boolean(step?.zta.some((z) => z.decision === "DENY"));

  const events = useMemo(() => {
    const out: LogEvent[] = [];
    round.timeline.slice(0, stepIdx + 1).forEach((s) => {
      if (s.red_action !== "WAIT")
        out.push({ step: s.step, text: `RED ${s.red_action}`, cls: "text-red-ops" });
      if (s.detected) out.push({ step: s.step, text: "BLUE DETECTED", cls: "text-hud-active" });
      s.defense_actions.forEach((a) =>
        out.push({ step: s.step, text: `DEF ${defenseLabel(a)}`, cls: "text-ok" }),
      );
      const restricted = s.zta.filter((z) => z.restrictive);
      if (restricted.length > 0)
        out.push({
          step: s.step,
          text: `ZTA ${restricted.map((z) => `${z.domain}:${z.decision}`).join(" ")}`,
          cls: "text-warn",
        });
    });
    return out.reverse();
  }, [round, stepIdx]);

  return (
    <HudFrame title="Event Log" accent={attacking || deny ? "red" : "none"} className="w-64">
      <ul className="max-h-32 space-y-0.5 overflow-y-auto p-2" aria-live="polite">
        {events.length === 0 && <li className="font-mono text-[10px] text-text-low">no events</li>}
        {events.map((e, i) => (
          <li key={i} className="flex gap-2 font-mono text-[10px]">
            <span className="shrink-0 text-text-low">{String(e.step).padStart(2, "0")}</span>
            <span className={`truncate ${e.cls}`}>{e.text}</span>
          </li>
        ))}
      </ul>
    </HudFrame>
  );
}

function CompactOverlay() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const round = getRound(roundIdx);
  const step = getStep(roundIdx, stepIdx);
  if (!step) return null;

  const restricted = step.zta.filter((z) => z.restrictive);
  const defense = step.defense_actions[0];

  return (
    <div className="grid grid-cols-2 gap-1.5">
      <HudFrame
        title="Suspicion"
        accent={step.detected ? "cyan" : "blue"}
        className="min-w-0"
        titleRight={<span className="font-mono text-[10px] text-text-hi">{step.suspicion.toFixed(2)}</span>}
      >
        <div className="p-2">
          <div className="h-1.5 bg-surface-2">
            <div className="h-full bg-blue-def" style={{ width: `${Math.round(step.suspicion * 100)}%` }} />
          </div>
        </div>
      </HudFrame>
      <HudFrame title="ZTA" accent={restricted.length ? "red" : "cyan"} className="min-w-0">
        <div className="flex h-full items-center justify-between gap-2 p-2 font-mono text-[10px]">
          <span className={restricted.length ? "text-warn" : "text-ok"}>
            {restricted.length ? `${restricted.length} restricted` : "all clear"}
          </span>
          <span className="text-text-low">{step.zta.length} domains</span>
        </div>
      </HudFrame>
      <HudFrame title="Telemetry" className="min-w-0">
        <div className="grid grid-cols-2 gap-1 p-2 font-mono text-[10px]">
          <span className="text-text-low">compute</span>
          <span className="text-right text-text-mid">{step.budgets.blue_compute_budget.toFixed(2)}</span>
          <span className="text-text-low">power</span>
          <span className="text-right text-text-mid">{step.budgets.blue_power_budget.toFixed(2)}</span>
        </div>
      </HudFrame>
      <HudFrame title="Event" accent={step.red_action !== "WAIT" ? "red" : "none"} className="min-w-0">
        <p className="truncate p-2 font-mono text-[10px] text-text-mid">
          {defense ? defenseLabel(defense) : `${round.attack.name}:${step.red_action}`}
        </p>
      </HudFrame>
    </div>
  );
}

/**
 * 창-밖-창 배치 (이미지 #11): 메인 씬 프레임 경계에 걸치는 위성 패널들.
 * 1440px 미만에서는 겹침 오프셋을 줄여 도킹에 가깝게 수렴.
 */
export function Satellites() {
  return (
    <>
      <div className="pointer-events-auto absolute left-2 right-2 top-2 z-20 hidden max-[1023px]:block">
        <CompactOverlay />
      </div>
      <div className="pointer-events-auto absolute -left-3 top-8 z-20 max-[1023px]:hidden max-[1439px]:-left-2 max-[1439px]:scale-90 xl:-left-5">
        <SuspicionSparkline />
      </div>
      <div className="pointer-events-auto absolute -right-3 top-24 z-20 max-[1023px]:hidden max-[1439px]:-right-2 max-[1439px]:scale-90 xl:-right-5">
        <ZtaPolicyLane />
      </div>
      <div className="pointer-events-auto absolute -left-2 bottom-24 z-20 max-[1023px]:hidden max-[1439px]:-left-1 max-[1439px]:scale-90 xl:-left-4">
        <TelemetryFeed />
      </div>
      <div className="pointer-events-auto absolute -right-2 bottom-10 z-20 max-[1023px]:hidden max-[1439px]:-right-1 max-[1439px]:scale-90 xl:-right-4">
        <EventLog />
      </div>
    </>
  );
}
