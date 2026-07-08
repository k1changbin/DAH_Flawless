import raw from "../../data/frontend/combat_replay.json";
import type { CombatReplay } from "./types/replay";

export const replay = raw as unknown as CombatReplay;

export function getRound(roundIdx: number) {
  return replay.rounds[roundIdx];
}

export function getStep(roundIdx: number, stepIdx: number) {
  const round = replay.rounds[roundIdx];
  if (!round || round.timeline.length === 0) return null;
  const clamped = Math.min(Math.max(stepIdx, 0), round.timeline.length - 1);
  return round.timeline[clamped];
}
