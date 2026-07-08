import { create } from "zustand";
import { replay } from "../data";

export type Focus = "RED" | "BLUE" | null;

interface ReplayState {
  entered: boolean;
  roundIdx: number;
  stepIdx: number;
  playing: boolean;
  focus: Focus;

  enter: () => void;
  exitToLanding: () => void;

  setRound: (idx: number) => void;
  setStep: (idx: number) => void;
  togglePlay: () => void;
  stop: () => void;
  next: () => void;
  prev: () => void;
  setFocus: (focus: Focus) => void;
  toggleFocus: (side: "RED" | "BLUE") => void;
}

function stepCount(roundIdx: number): number {
  return replay.rounds[roundIdx]?.timeline.length ?? 0;
}

export const useReplayStore = create<ReplayState>((set, get) => ({
  entered: false,
  roundIdx: 0,
  stepIdx: 0,
  playing: false,
  focus: null,

  enter: () => set({ entered: true }),
  exitToLanding: () => set({ entered: false, playing: false, focus: null }),

  setRound: (idx) => {
    if (idx < 0 || idx >= replay.rounds.length) return;
    set({ roundIdx: idx, stepIdx: 0, playing: false });
  },

  setStep: (idx) => {
    const max = stepCount(get().roundIdx) - 1;
    set({ stepIdx: Math.min(Math.max(idx, 0), Math.max(max, 0)) });
  },

  togglePlay: () => {
    const { stepIdx, roundIdx, playing } = get();
    // 끝에서 재생 누르면 처음부터
    if (!playing && stepIdx >= stepCount(roundIdx) - 1) {
      set({ stepIdx: 0, playing: true });
    } else {
      set({ playing: !playing });
    }
  },

  stop: () => set({ playing: false }),

  next: () => {
    const { stepIdx, roundIdx } = get();
    const max = stepCount(roundIdx) - 1;
    if (stepIdx >= max) {
      set({ playing: false });
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
