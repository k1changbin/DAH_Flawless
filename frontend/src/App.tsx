import { useEffect } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { CommandBar } from "./components/CommandBar";
import { SidePanel } from "./components/SidePanel";
import { CenterScene } from "./components/CenterScene";
import { Satellites } from "./components/Satellites";
import { TimelineLane } from "./components/TimelineLane";
import { Mugyeol } from "./components/Mugyeol";
import { Landing } from "./components/Landing";
import { ResultsPage } from "./components/ResultsPage";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useReplayStore } from "./store/useReplayStore";

const PLAY_INTERVAL_MS = 1100;
const EASE_OUT = [0.23, 1, 0.32, 1] as const;

function Dashboard() {
  const playing = useReplayStore((s) => s.playing);
  const playbackSpeed = useReplayStore((s) => s.playbackSpeed);
  const reduce = useReducedMotion();

  // 재생 틱
  useEffect(() => {
    if (!playing) return;
    const interval = Math.max(70, PLAY_INTERVAL_MS / Math.min(playbackSpeed, 8));
    const id = setInterval(() => {
      const store = useReplayStore.getState();
      if (store.playbackSpeed >= 8) {
        store.nextRound(Math.max(1, Math.floor(store.playbackSpeed / 8)));
      } else {
        store.next();
      }
    }, interval);
    return () => clearInterval(id);
  }, [playing, playbackSpeed]);

  // 키보드: Space 재생, ←/→ 스텝, Esc 포커스 해제
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;
      const store = useReplayStore.getState();
      switch (e.key) {
        case " ":
          e.preventDefault();
          store.togglePlay();
          break;
        case "ArrowRight":
          store.next();
          break;
        case "ArrowLeft":
          store.prev();
          break;
        case "Escape":
          store.setFocus(null);
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // 부팅 시퀀스 타이밍 (스펙 7.1). reduced-motion이면 즉시 표시.
  const boot = (delay: number, from: { x?: number; y?: number }) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, ...from },
          animate: { opacity: 1, x: 0, y: 0 },
          transition: { duration: 0.3, delay, ease: EASE_OUT },
        };

  return (
    <motion.div
      className="dashboard-shell relative flex h-full flex-col overflow-hidden"
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="dashboard-backdrop" aria-hidden />
      <motion.div {...boot(0.15, { y: -8 })}>
        <CommandBar />
      </motion.div>
      <main className="relative z-10 flex min-h-0 flex-1 gap-2 p-2 max-[1023px]:p-1">
        <motion.div className="flex shrink-0" {...boot(0.4, { x: -16 })}>
          <SidePanel side="RED" />
        </motion.div>
        <motion.div
          className="relative min-w-0 flex-1"
          {...(reduce
            ? {}
            : {
                initial: { opacity: 0 },
                animate: { opacity: 1 },
                transition: { duration: 0.8, delay: 0.6 },
              })}
        >
          <CenterScene />
          <Satellites />
        </motion.div>
        <motion.div className="flex shrink-0" {...boot(0.4, { x: 16 })}>
          <SidePanel side="BLUE" />
        </motion.div>
      </main>
      <motion.div {...boot(0.4, { y: 16 })}>
        <TimelineLane />
      </motion.div>
    </motion.div>
  );
}

export default function App() {
  const entered = useReplayStore((s) => s.entered);
  const screen = useReplayStore((s) => s.screen);

  return (
    <ErrorBoundary>
      <div className="h-full">
        <div className="bg-battle-grid" aria-hidden />
        <AnimatePresence mode="wait">
          {!entered ? (
            <Landing key="landing" />
          ) : screen === "results" ? (
            <ResultsPage key="results" />
          ) : (
            <Dashboard key="dashboard" />
          )}
        </AnimatePresence>
        {entered && <Mugyeol />}
      </div>
    </ErrorBoundary>
  );
}
