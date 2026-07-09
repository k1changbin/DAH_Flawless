import type { CombatReplay, ReplayRound, WinnerSide } from "./types/replay";

export const MAX_LEARNING_ROUNDS = 2000;

export type MarkerKind = "start" | "early" | "sample" | "first-blue" | "shift" | "current" | "final";

export interface LearningMarker {
  index: number;
  round: number;
  kind: MarkerKind;
  side: WinnerSide;
  label: string;
  detail: string;
}

export interface LearningBin {
  fromRound: number;
  toRound: number;
  dominant: WinnerSide;
  blueRate: number;
  redRate: number;
  drawRate: number;
  score: number;
}

export interface LearningWindow {
  index: number;
  fromRound: number;
  toRound: number;
  side: WinnerSide;
  label: string;
  detail: string;
  counts: Record<WinnerSide, number>;
  diff: number;
}

export interface LearningProfile {
  totalRounds: number;
  visibleRounds: number;
  capped: boolean;
  markerCount: number;
  firstBlueIndex: number | null;
  shiftIndex: number | null;
  phase: string;
  winnerCounts: Record<WinnerSide, number>;
  currentCounts: Record<WinnerSide, number>;
  markers: LearningMarker[];
  bins: LearningBin[];
  windows: LearningWindow[];
}

const EMPTY_COUNTS: Record<WinnerSide, number> = { BLUE: 0, RED: 0, DRAW: 0 };

function sideOf(round: ReplayRound): WinnerSide {
  return round.outcome.winner_side;
}

function addCount(counts: Record<WinnerSide, number>, side: WinnerSide): void {
  counts[side] += 1;
}

function dominantSide(counts: Record<WinnerSide, number>): WinnerSide {
  if (counts.BLUE >= counts.RED && counts.BLUE >= counts.DRAW) return "BLUE";
  if (counts.RED >= counts.BLUE && counts.RED >= counts.DRAW) return "RED";
  return "DRAW";
}

function cloneCounts(): Record<WinnerSide, number> {
  return { ...EMPTY_COUNTS };
}

function windowSize(total: number): number {
  if (total >= 1000) return 100;
  if (total >= 500) return 80;
  if (total >= 240) return 40;
  if (total >= 120) return 24;
  if (total >= 60) return 10;
  if (total >= 20) return 5;
  return Math.max(3, Math.min(total, 4));
}

function sampleRatios(total: number): number[] {
  if (total <= 10) return [0.45, 0.7];
  if (total <= 30) return [0.16, 0.32, 0.5, 0.68, 0.84];
  return [0.08, 0.16, 0.28, 0.4, 0.52, 0.64, 0.76, 0.88];
}

function findShiftIndex(rounds: ReplayRound[], firstBlueIndex: number | null): number | null {
  if (firstBlueIndex === null) return null;
  const size = windowSize(rounds.length);
  let priorRedPressure = false;

  for (let end = size - 1; end < rounds.length; end += 1) {
    const counts = cloneCounts();
    for (let i = end - size + 1; i <= end; i += 1) {
      addCount(counts, sideOf(rounds[i]));
    }
    if (counts.RED > counts.BLUE) priorRedPressure = true;
    if (priorRedPressure && counts.BLUE > counts.RED) return end;
  }

  return firstBlueIndex;
}

function markerKind(index: number, total: number, firstBlueIndex: number | null, shiftIndex: number | null, currentIndex: number): MarkerKind {
  if (index === currentIndex) return "current";
  if (index === shiftIndex) return "shift";
  if (index === firstBlueIndex) return "first-blue";
  if (index === 0) return "start";
  if (index === total - 1) return "final";
  if (index <= Math.max(1, Math.floor(total * 0.12))) return "early";
  return "sample";
}

function markerLabel(kind: MarkerKind): string {
  switch (kind) {
    case "start":
      return "START";
    case "early":
      return "EARLY";
    case "first-blue":
      return "FIRST BLUE";
    case "shift":
      return "SHIFT";
    case "current":
      return "NOW";
    case "final":
      return "FINAL";
    default:
      return "SNAP";
  }
}

function phaseLabel(currentIndex: number, firstBlueIndex: number | null, shiftIndex: number | null): string {
  if (firstBlueIndex === null || currentIndex < firstBlueIndex) return "RED PRESSURE";
  if (shiftIndex !== null && currentIndex >= shiftIndex) return "BLUE MOMENTUM";
  return "BLUE LEARNING";
}

function buildBins(rounds: ReplayRound[]): LearningBin[] {
  if (rounds.length === 0) return [];
  const binCount = Math.min(56, Math.max(1, rounds.length));
  const bins: LearningBin[] = [];

  for (let bin = 0; bin < binCount; bin += 1) {
    const start = Math.floor((bin * rounds.length) / binCount);
    const end = Math.max(start + 1, Math.floor(((bin + 1) * rounds.length) / binCount));
    const counts = cloneCounts();
    for (let i = start; i < end; i += 1) {
      addCount(counts, sideOf(rounds[i]));
    }
    const total = Math.max(1, end - start);
    bins.push({
      fromRound: rounds[start].round,
      toRound: rounds[end - 1].round,
      dominant: dominantSide(counts),
      blueRate: counts.BLUE / total,
      redRate: counts.RED / total,
      drawRate: counts.DRAW / total,
      score: (counts.BLUE - counts.RED) / total,
    });
  }

  return bins;
}

function buildRollingWindows(rounds: ReplayRound[], shiftIndex: number | null): LearningWindow[] {
  if (rounds.length === 0) return [];
  const size = windowSize(rounds.length);
  const windows: LearningWindow[] = [];
  let bestRed: { start: number; counts: Record<WinnerSide, number>; diff: number } | null = null;
  let bestBlue: { start: number; counts: Record<WinnerSide, number>; diff: number } | null = null;

  for (let start = 0; start < rounds.length; start += 1) {
    const end = Math.min(rounds.length, start + size);
    if (end - start < Math.min(size, rounds.length)) break;
    const counts = cloneCounts();
    for (let i = start; i < end; i += 1) addCount(counts, sideOf(rounds[i]));
    const diff = counts.BLUE - counts.RED;
    if (bestBlue === null || diff > bestBlue.diff) {
      bestBlue = { start, counts, diff };
    }
    if (bestRed === null || -diff > bestRed.diff) {
      bestRed = { start, counts, diff: -diff };
    }
  }

  function pushWindow(
    item: { start: number; counts: Record<WinnerSide, number>; diff: number } | null,
    label: string,
    side: WinnerSide,
  ) {
    if (item === null) return;
    const end = Math.min(rounds.length - 1, item.start + size - 1);
    windows.push({
      index: item.start,
      fromRound: rounds[item.start].round,
      toRound: rounds[end].round,
      side,
      label,
      counts: item.counts,
      diff: item.diff,
      detail: `BLUE ${item.counts.BLUE} / RED ${item.counts.RED} / DRAW ${item.counts.DRAW}`,
    });
  }

  pushWindow(bestRed, "RED PEAK", "RED");

  if (shiftIndex !== null) {
    const start = Math.max(0, shiftIndex - size + 1);
    const end = Math.min(rounds.length - 1, shiftIndex);
    const counts = cloneCounts();
    for (let i = start; i <= end; i += 1) addCount(counts, sideOf(rounds[i]));
    windows.push({
      index: start,
      fromRound: rounds[start].round,
      toRound: rounds[end].round,
      side: "BLUE",
      label: "SHIFT",
      counts,
      diff: Math.abs(counts.BLUE - counts.RED),
      detail: `BLUE ${counts.BLUE} / RED ${counts.RED} / DRAW ${counts.DRAW}`,
    });
  }

  pushWindow(bestBlue, "BLUE PEAK", "BLUE");

  return windows.filter(
    (item, index, all) => all.findIndex((other) => other.label === item.label && other.index === item.index) === index,
  );
}

export function effectiveRoundLimit(replay: CombatReplay, requestedRoundLimit: number): number {
  const requested = Number.isFinite(requestedRoundLimit) ? Math.floor(requestedRoundLimit) : MAX_LEARNING_ROUNDS;
  return Math.min(Math.max(requested, 1), MAX_LEARNING_ROUNDS, Math.max(replay.rounds.length, 1));
}

export function buildLearningProfile(
  replay: CombatReplay,
  currentRoundIdx: number,
  requestedRoundLimit = MAX_LEARNING_ROUNDS,
): LearningProfile {
  const limit = effectiveRoundLimit(replay, requestedRoundLimit);
  const rounds = replay.rounds.slice(0, limit);
  const total = rounds.length;
  const safeCurrent = Math.min(Math.max(currentRoundIdx, 0), Math.max(total - 1, 0));
  const firstBlueIndex = rounds.findIndex((round) => sideOf(round) === "BLUE");
  const normalizedFirstBlue = firstBlueIndex >= 0 ? firstBlueIndex : null;
  const shiftIndex = findShiftIndex(rounds, normalizedFirstBlue);

  const indices = new Set<number>();
  if (total > 0) {
    indices.add(0);
    if (total > 3) indices.add(1);
    for (const ratio of sampleRatios(total)) {
      indices.add(Math.min(total - 1, Math.max(0, Math.round((total - 1) * ratio))));
    }
    if (normalizedFirstBlue !== null) indices.add(normalizedFirstBlue);
    if (shiftIndex !== null) indices.add(shiftIndex);
    indices.add(safeCurrent);
    indices.add(total - 1);
  }

  const winnerCounts = cloneCounts();
  const currentCounts = cloneCounts();
  rounds.forEach((round, index) => {
    const side = sideOf(round);
    addCount(winnerCounts, side);
    if (index <= safeCurrent) addCount(currentCounts, side);
  });

  const markers = [...indices]
    .sort((a, b) => a - b)
    .map((index) => {
      const round = rounds[index];
      const kind = markerKind(index, total, normalizedFirstBlue, shiftIndex, safeCurrent);
      return {
        index,
        round: round.round,
        kind,
        side: sideOf(round),
        label: markerLabel(kind),
        detail: `${round.attack.name} / ${round.outcome.winner_side}:${round.outcome.winner_detail}`,
      };
    });

  return {
    totalRounds: replay.rounds.length,
    visibleRounds: total,
    capped: replay.rounds.length > MAX_LEARNING_ROUNDS,
    markerCount: markers.length,
    firstBlueIndex: normalizedFirstBlue,
    shiftIndex,
    phase: phaseLabel(safeCurrent, normalizedFirstBlue, shiftIndex),
    winnerCounts,
    currentCounts,
    markers,
    bins: buildBins(rounds),
    windows: buildRollingWindows(rounds, shiftIndex),
  };
}
