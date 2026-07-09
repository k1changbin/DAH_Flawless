import { buildLearningProfile, effectiveRoundLimit, type LearningWindow } from "./learning";
import type { CombatReplay, ReplayRound, WinnerSide, ZtaDomain } from "./types/replay";

export interface CountItem {
  key: string;
  count: number;
  rate: number;
}

export interface ResultTrendPoint {
  index: number;
  round: number;
  blue: number;
  red: number;
  draw: number;
  lead: number;
}

export interface ResultBin {
  index: number;
  fromRound: number;
  toRound: number;
  dominant: WinnerSide;
  counts: Record<WinnerSide, number>;
  attackDominant: string;
  policyDominant: string;
  blueRate: number;
  redRate: number;
}

export interface PolicyDomainRow {
  domain: ZtaDomain;
  total: number;
  decisions: CountItem[];
}

export interface ResultProfile {
  totalRounds: number;
  visibleRounds: number;
  currentRound: number;
  winnerCounts: Record<WinnerSide, number>;
  winnerItems: CountItem[];
  attackItems: CountItem[];
  goalItems: CountItem[];
  policyItems: CountItem[];
  policyRows: PolicyDomainRow[];
  trend: ResultTrendPoint[];
  bins: ResultBin[];
  windows: LearningWindow[];
  firstBlueRound: number | null;
  shiftRound: number | null;
  bluePeakRound: number | null;
  redPeakRound: number | null;
}

const SIDES: WinnerSide[] = ["BLUE", "RED", "DRAW"];
const DOMAINS: ZtaDomain[] = ["command", "mission", "telemetry"];

function emptyWinnerCounts(): Record<WinnerSide, number> {
  return { BLUE: 0, RED: 0, DRAW: 0 };
}

function addWinner(counts: Record<WinnerSide, number>, side: WinnerSide): void {
  counts[side] += 1;
}

function addString(counts: Record<string, number>, key: string | null | undefined): void {
  const safeKey = key && key.trim() ? key : "UNKNOWN";
  counts[safeKey] = (counts[safeKey] ?? 0) + 1;
}

function countItems(counts: Record<string, number>, total: number): CountItem[] {
  return Object.entries(counts)
    .map(([key, count]) => ({ key, count, rate: total > 0 ? count / total : 0 }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

function winnerItems(counts: Record<WinnerSide, number>, total: number): CountItem[] {
  return SIDES.map((side) => ({
    key: side,
    count: counts[side],
    rate: total > 0 ? counts[side] / total : 0,
  }));
}

function dominantWinner(counts: Record<WinnerSide, number>): WinnerSide {
  if (counts.BLUE >= counts.RED && counts.BLUE >= counts.DRAW) return "BLUE";
  if (counts.RED >= counts.BLUE && counts.RED >= counts.DRAW) return "RED";
  return "DRAW";
}

function dominantString(counts: Record<string, number>): string {
  return countItems(counts, Object.values(counts).reduce((sum, count) => sum + count, 0))[0]?.key ?? "UNKNOWN";
}

function buildTrend(rounds: ReplayRound[]): ResultTrendPoint[] {
  const trend: ResultTrendPoint[] = [];
  const counts = emptyWinnerCounts();
  const sampleEvery = Math.max(1, Math.ceil(rounds.length / 160));

  rounds.forEach((round, index) => {
    addWinner(counts, round.outcome.winner_side);
    if (index % sampleEvery === 0 || index === rounds.length - 1) {
      trend.push({
        index,
        round: round.round,
        blue: counts.BLUE,
        red: counts.RED,
        draw: counts.DRAW,
        lead: counts.BLUE - counts.RED,
      });
    }
  });

  return trend;
}

function buildBins(rounds: ReplayRound[]): ResultBin[] {
  const binCount = Math.min(72, Math.max(1, Math.ceil(rounds.length / 18)));
  const bins: ResultBin[] = [];

  for (let bin = 0; bin < binCount; bin += 1) {
    const start = Math.floor((bin * rounds.length) / binCount);
    const end = Math.max(start + 1, Math.floor(((bin + 1) * rounds.length) / binCount));
    const counts = emptyWinnerCounts();
    const attacks: Record<string, number> = {};
    const policies: Record<string, number> = {};

    for (let i = start; i < end; i += 1) {
      const round = rounds[i];
      addWinner(counts, round.outcome.winner_side);
      addString(attacks, round.attack.name);
      for (const [decision, count] of Object.entries(round.zta_policy?.decision_counts ?? {})) {
        policies[decision] = (policies[decision] ?? 0) + Number(count);
      }
    }

    const total = Math.max(1, end - start);
    bins.push({
      index: start,
      fromRound: rounds[start].round,
      toRound: rounds[end - 1].round,
      dominant: dominantWinner(counts),
      counts,
      attackDominant: dominantString(attacks),
      policyDominant: dominantString(policies),
      blueRate: counts.BLUE / total,
      redRate: counts.RED / total,
    });
  }

  return bins;
}

export function buildResultProfile(
  replay: CombatReplay,
  currentRoundIdx: number,
  requestedRoundLimit: number,
): ResultProfile {
  const limit = effectiveRoundLimit(replay, requestedRoundLimit);
  const rounds = replay.rounds.slice(0, limit);
  const total = rounds.length;
  const winnerCounts = emptyWinnerCounts();
  const attacks: Record<string, number> = {};
  const goals: Record<string, number> = {};
  const policies: Record<string, number> = {};
  const domainPolicy: Record<ZtaDomain, Record<string, number>> = {
    command: {},
    mission: {},
    telemetry: {},
  };

  rounds.forEach((round) => {
    addWinner(winnerCounts, round.outcome.winner_side);
    addString(attacks, round.attack.name);
    addString(goals, String(round.goal?.id ?? round.outcome.goal_id ?? "UNKNOWN"));
    for (const [decision, count] of Object.entries(round.zta_policy?.decision_counts ?? {})) {
      policies[decision] = (policies[decision] ?? 0) + Number(count);
    }
    for (const domain of DOMAINS) {
      const decision = round.zta_policy?.per_domain?.[domain]?.decision ?? "UNKNOWN";
      addString(domainPolicy[domain], decision);
    }
  });

  const learning = buildLearningProfile(replay, currentRoundIdx, requestedRoundLimit);
  const bluePeak = learning.windows.find((item) => item.label === "BLUE PEAK") ?? null;
  const redPeak = learning.windows.find((item) => item.label === "RED PEAK") ?? null;

  return {
    totalRounds: replay.rounds.length,
    visibleRounds: total,
    currentRound: rounds[Math.min(Math.max(currentRoundIdx, 0), Math.max(total - 1, 0))]?.round ?? 1,
    winnerCounts,
    winnerItems: winnerItems(winnerCounts, total),
    attackItems: countItems(attacks, total),
    goalItems: countItems(goals, total),
    policyItems: countItems(policies, Object.values(policies).reduce((sum, count) => sum + count, 0)),
    policyRows: DOMAINS.map((domain) => {
      const total = Object.values(domainPolicy[domain]).reduce((sum, count) => sum + count, 0);
      return { domain, total, decisions: countItems(domainPolicy[domain], total) };
    }),
    trend: buildTrend(rounds),
    bins: buildBins(rounds),
    windows: learning.windows,
    firstBlueRound:
      learning.firstBlueIndex === null ? null : rounds[learning.firstBlueIndex]?.round ?? null,
    shiftRound: learning.shiftIndex === null ? null : rounds[learning.shiftIndex]?.round ?? null,
    bluePeakRound: bluePeak?.fromRound ?? null,
    redPeakRound: redPeak?.fromRound ?? null,
  };
}
