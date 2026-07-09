import { create } from "zustand";
import {
  DEFAULT_RUN_ID,
  getReplay,
  getRun,
  getRunBySeedScenario,
  type ReplayScenarioId,
} from "../data";
import { MAX_LEARNING_ROUNDS, effectiveRoundLimit } from "../learning";

export type Focus = "RED" | "BLUE" | null;
export type Screen = "replay" | "results";

export const PLAYBACK_SPEEDS = [1, 2, 4, 8, 16, 64] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

interface ReplayState {
  entered: boolean;
  screen: Screen;
  runId: string;
  seed: number;
  scenario: ReplayScenarioId;
  roundLimit: number;
  playbackSpeed: PlaybackSpeed;
  roundIdx: number;
  stepIdx: number;
  playing: boolean;
  focus: Focus;

  enter: () => void;
  exitToLanding: () => void;
  showReplay: () => void;
  showResults: () => void;

  setRunId: (runId: string) => void;
  setRunSelection: (seed: number, scenario: ReplayScenarioId) => void;
  setRoundLimit: (roundLimit: number) => void;
  setPlaybackSpeed: (speed: PlaybackSpeed) => void;
  setRound: (idx: number) => void;
  setStep: (idx: number) => void;
  nextRound: (by?: number) => void;
  togglePlay: () => void;
  stop: () => void;
  next: () => void;
  prev: () => void;
  setFocus: (focus: Focus) => void;
  toggleFocus: (side: "RED" | "BLUE") => void;
}

function runLimit(runId: string, roundLimit: number): number {
  return effectiveRoundLimit(getReplay(runId), roundLimit);
}

function requestedRoundLimit(roundLimit: number): number {
  const requested = Number.isFinite(roundLimit) ? Math.floor(roundLimit) : MAX_LEARNING_ROUNDS;
  return Math.min(Math.max(requested, 1), MAX_LEARNING_ROUNDS);
}

function stepCount(runId: string, roundIdx: number): number {
  return getReplay(runId).rounds[roundIdx]?.timeline.length ?? 0;
}

const defaultRun = getRun(DEFAULT_RUN_ID);

export const useReplayStore = create<ReplayState>((set, get) => ({
  entered: false,
  screen: "replay",
  runId: defaultRun.id,
  seed: defaultRun.seed,
  scenario: defaultRun.scenario,
  roundLimit: MAX_LEARNING_ROUNDS,
  playbackSpeed: 1,
  roundIdx: 0,
  stepIdx: 0,
  playing: false,
  focus: null,

  enter: () => set({ entered: true, screen: "replay" }),
  exitToLanding: () => set({ entered: false, screen: "replay", playing: false, focus: null }),
  showReplay: () => set({ screen: "replay" }),
  showResults: () => set({ screen: "results", playing: false, focus: null }),

  setRunId: (runId) => {
    const run = getRun(runId);
    const requested = requestedRoundLimit(get().roundLimit);
    set({
      runId: run.id,
      seed: run.seed,
      scenario: run.scenario,
      roundLimit: requested,
      roundIdx: 0,
      stepIdx: 0,
      playing: false,
      screen: "replay",
      focus: null,
    });
  },

  setRunSelection: (seed, scenario) => {
    const run = getRunBySeedScenario(seed, scenario);
    const requested = requestedRoundLimit(get().roundLimit);
    set({
      runId: run.id,
      seed: run.seed,
      scenario: run.scenario,
      roundLimit: requested,
      roundIdx: 0,
      stepIdx: 0,
      playing: false,
      screen: "replay",
      focus: null,
    });
  },

  setRoundLimit: (roundLimit) => {
    const { runId, roundIdx } = get();
    const requested = requestedRoundLimit(roundLimit);
    const effective = runLimit(runId, requested);
    set({
      roundLimit: requested,
      roundIdx: Math.min(roundIdx, effective - 1),
      stepIdx: 0,
      playing: false,
    });
  },

  setPlaybackSpeed: (speed) => set({ playbackSpeed: PLAYBACK_SPEEDS.includes(speed) ? speed : 1 }),

  setRound: (idx) => {
    const { runId, roundLimit } = get();
    if (idx < 0 || idx >= runLimit(runId, roundLimit)) return;
    set({ roundIdx: idx, stepIdx: 0, playing: false, screen: "replay" });
  },

  setStep: (idx) => {
    const { runId, roundIdx } = get();
    const max = stepCount(runId, roundIdx) - 1;
    set({ stepIdx: Math.min(Math.max(idx, 0), Math.max(max, 0)) });
  },

  togglePlay: () => {
    const { stepIdx, roundIdx, playing, runId } = get();
    // 끝에서 재생 누르면 처음부터
    if (!playing && stepIdx >= stepCount(runId, roundIdx) - 1) {
      set({ stepIdx: 0, playing: true });
    } else {
      set({ playing: !playing });
    }
  },

  stop: () => set({ playing: false }),

  nextRound: (by = 1) => {
    const { roundIdx, runId, roundLimit } = get();
    const lastRoundIdx = runLimit(runId, roundLimit) - 1;
    if (roundIdx >= lastRoundIdx) {
      set({ playing: false });
      return;
    }
    const jump = Number.isFinite(by) ? Math.max(1, Math.floor(by)) : 1;
    set({ roundIdx: Math.min(roundIdx + jump, lastRoundIdx), stepIdx: 0 });
  },

  next: () => {
    const { stepIdx, roundIdx, runId, roundLimit } = get();
    const max = stepCount(runId, roundIdx) - 1;
    if (stepIdx >= max) {
      const lastRoundIdx = runLimit(runId, roundLimit) - 1;
      if (roundIdx < lastRoundIdx) {
        set({ roundIdx: roundIdx + 1, stepIdx: 0 });
      } else {
        set({ playing: false });
      }
    } else {
      set({ stepIdx: stepIdx + 1 });
    }
  },

  prev: () => {
    const { stepIdx } = get();
    set({ stepIdx: Math.max(stepIdx - 1, 0), playing: false });
  },

  setFocus: (focus) => set({ focus }),

  toggleFocus: (side) => {
    set({ focus: get().focus === side ? null : side });
  },
}));
