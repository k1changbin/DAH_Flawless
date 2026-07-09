import rawSeed42Clean from "../../data/frontend/runs/seed42_clean_start_2000.json";
import rawSeed42Satcom from "../../data/frontend/runs/seed42_satcom_delay.json";
import rawSeed42Telemetry from "../../data/frontend/runs/seed42_telemetry_conflict.json";
import rawSeed99Clean from "../../data/frontend/runs/seed99_clean_start.json";
import rawSeed99Satcom from "../../data/frontend/runs/seed99_satcom_delay.json";
import rawSeed99Telemetry from "../../data/frontend/runs/seed99_telemetry_conflict.json";
import type { CombatReplay } from "./types/replay";

export type ReplayScenarioId = "clean_start" | "satcom_delay" | "telemetry_conflict";

export interface ReplayRun {
  id: string;
  seed: number;
  scenario: ReplayScenarioId;
  scenarioLabel: string;
  scenarioDescription: string;
  replay: CombatReplay;
}

const scenarioLabels: Record<ReplayScenarioId, string> = {
  clean_start: "Clean start",
  satcom_delay: "SATCOM delay",
  telemetry_conflict: "Telemetry conflict",
};

const scenarioDescriptions: Record<ReplayScenarioId, string> = {
  clean_start: "Healthy baseline: full capability, normal link, availability 1.0.",
  satcom_delay: "SATCOM stress: high latency, packet loss, jitter, ACK timing pressure.",
  telemetry_conflict: "Telemetry stress: physically inconsistent battery, drain, and motor signals.",
};

function run(seed: number, scenario: ReplayScenarioId, replay: unknown): ReplayRun {
  const typedReplay = replay as CombatReplay;
  typedReplay.source = {
    ...typedReplay.source,
    seed,
    scenario,
    scenario_label: scenarioLabels[scenario],
    scenario_description: scenarioDescriptions[scenario],
  };

  return {
    id: `seed${seed}-${scenario}`,
    seed,
    scenario,
    scenarioLabel: scenarioLabels[scenario],
    scenarioDescription: scenarioDescriptions[scenario],
    replay: typedReplay,
  };
}

export const RUNS: ReplayRun[] = [
  run(42, "clean_start", rawSeed42Clean),
  run(42, "satcom_delay", rawSeed42Satcom),
  run(42, "telemetry_conflict", rawSeed42Telemetry),
  run(99, "clean_start", rawSeed99Clean),
  run(99, "satcom_delay", rawSeed99Satcom),
  run(99, "telemetry_conflict", rawSeed99Telemetry),
];

export const SEED_OPTIONS = [42, 99] as const;

export const SCENARIO_OPTIONS = (["clean_start", "satcom_delay", "telemetry_conflict"] as const).map(
  (id) => ({
    id,
    label: scenarioLabels[id],
  }),
);

export const DEFAULT_RUN_ID = RUNS[0].id;

export const replay = RUNS[0].replay;

export function getRun(runId: string): ReplayRun {
  return RUNS.find((item) => item.id === runId) ?? RUNS[0];
}

export function getRunBySeedScenario(seed: number, scenario: ReplayScenarioId): ReplayRun {
  return RUNS.find((item) => item.seed === seed && item.scenario === scenario) ?? RUNS[0];
}

export function getReplay(runId: string): CombatReplay {
  return getRun(runId).replay;
}

export function getRound(runId: string, roundIdx: number) {
  return getReplay(runId).rounds[roundIdx];
}

export function getStep(runId: string, roundIdx: number, stepIdx: number) {
  const round = getReplay(runId).rounds[roundIdx];
  if (!round || round.timeline.length === 0) return null;
  const clamped = Math.min(Math.max(stepIdx, 0), round.timeline.length - 1);
  return round.timeline[clamped];
}
