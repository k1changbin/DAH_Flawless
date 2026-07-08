import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Microphone, PaperPlaneRight, X } from "@phosphor-icons/react";
import { replay, getRound } from "../data";
import { useReplayStore } from "../store/useReplayStore";
import { useMediaQuery } from "../hooks/useMediaQuery";

/* ---------- Web Speech 최소 타입 ---------- */

interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

function createRecognition(): Recognition | null {
  const w = window as unknown as Record<string, unknown>;
  const Ctor = (w.SpeechRecognition ?? w.webkitSpeechRecognition) as
    | (new () => Recognition)
    | undefined;
  if (!Ctor) return null;
  const rec = new Ctor();
  rec.lang = "ko-KR";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  return rec;
}

type MugyeolState = "idle" | "listening" | "thinking" | "speaking" | "error";

/** 첫 마운트에만 부팅 팝 딜레이 적용 */
let bootPopDone = false;

const WINDOW_W = 320;
const WINDOW_H = 410;
const WINDOW_MARGIN = 16;
const WINDOW_BOTTOM = 128;

interface WindowPosition {
  left: number;
  top: number;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  startLeft: number;
  startTop: number;
}

const QUICK_COMMANDS = ["3라운드 보여줘", "공격 뷰", "방어 뷰", "재생", "누가 이겼어"];

const HELP_TEXT = "이렇게 말해보세요: N라운드 보여줘 / 공격 뷰 / 방어 뷰 / 재생 / 정지 / 다음 / 이전 / 누가 이겼어 / 정책 보여줘";

/** 명령 매칭. 응답 문장을 돌려준다(null = 매칭 실패). */
function runCommand(text: string): string | null {
  const store = useReplayStore.getState();
  const t = text.trim().toLowerCase();

  const roundMatch = t.match(/(\d+)\s*라운드/);
  if (roundMatch) {
    const n = Number(roundMatch[1]);
    if (n >= 1 && n <= replay.rounds.length) {
      store.setRound(n - 1);
      return `${n}라운드로 이동했어요.`;
    }
    return `라운드는 1부터 ${replay.rounds.length}까지 있어요.`;
  }
  if (/(공격|레드|red)/.test(t)) {
    store.setFocus("RED");
    return "공격 패널을 열었어요.";
  }
  if (/(방어|블루|blue)/.test(t)) {
    store.setFocus("BLUE");
    return "방어 패널을 열었어요.";
  }
  if (/(재생|플레이|시작)/.test(t)) {
    if (!store.playing) store.togglePlay();
    return "재생할게요.";
  }
  if (/(정지|멈춰|스톱|일시)/.test(t)) {
    store.stop();
    return "멈췄어요.";
  }
  if (/다음/.test(t)) {
    store.next();
    return "다음 스텝이에요.";
  }
  if (/이전/.test(t)) {
    store.prev();
    return "이전 스텝이에요.";
  }
  if (/(누가 이겼|승자|승패|결과)/.test(t)) {
    const round = getRound(store.roundIdx);
    const side =
      round.outcome.winner_side === "BLUE"
        ? "블루 방어팀"
        : round.outcome.winner_side === "RED"
          ? "레드 공격팀"
          : "무승부";
    return `${round.round}라운드 결과는 ${side}. 세부 판정은 ${round.outcome.winner_detail}입니다.`;
  }
  if (/(제타|정책|zta)/.test(t)) {
    store.setFocus("BLUE");
    return "ZTA 정책은 우측 상단 위성 창과 방어 패널에서 볼 수 있어요.";
  }
  return null;
}

function defaultWindowPosition(): WindowPosition {
  return clampWindowPosition({
    left: window.innerWidth - WINDOW_W - WINDOW_MARGIN,
    top: window.innerHeight - WINDOW_H - WINDOW_BOTTOM,
  });
}

function clampWindowPosition(pos: WindowPosition): WindowPosition {
  const maxLeft = Math.max(WINDOW_MARGIN, window.innerWidth - WINDOW_W - WINDOW_MARGIN);
  const maxTop = Math.max(WINDOW_MARGIN, window.innerHeight - WINDOW_H - WINDOW_MARGIN);
  return {
    left: Math.min(Math.max(pos.left, WINDOW_MARGIN), maxLeft),
    top: Math.min(Math.max(pos.top, WINDOW_MARGIN), maxTop),
  };
}

export function Mugyeol() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<MugyeolState>("idle");
  const [transcript, setTranscript] = useState("");
  const [response, setResponse] = useState("안녕하세요, 무결이에요. 리플레이 조작을 도와드릴게요.");
  const [textInput, setTextInput] = useState("");
  const [windowPos, setWindowPos] = useState<WindowPosition | null>(null);
  const focus = useReplayStore((s) => s.focus);
  const sheetMode = useMediaQuery("(max-width: 1023px)");

  const recRef = useRef<Recognition | null>(null);
  const blobWrapRef = useRef<HTMLDivElement>(null);
  const audioCleanup = useRef<(() => void) | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const speechSupported = useRef<boolean | null>(null);
  if (speechSupported.current === null) {
    speechSupported.current = createRecognition() !== null;
  }

  const stopAudioMeter = useCallback(() => {
    audioCleanup.current?.();
    audioCleanup.current = null;
    if (blobWrapRef.current) blobWrapRef.current.style.transform = "";
  }, []);

  /** 마이크 볼륨 → 블롭 꿈틀 (rAF에서 직접 스타일, 리렌더 없음) */
  const startAudioMeter = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.frequencyBinCount);
      let raf = 0;
      const tick = () => {
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) {
          const v = (buf[i] - 128) / 128;
          sum += v * v;
        }
        const rms = Math.sqrt(sum / buf.length);
        if (blobWrapRef.current) {
          blobWrapRef.current.style.transform = `scale(${1 + Math.min(rms * 2.2, 0.35)})`;
        }
        raf = requestAnimationFrame(tick);
      };
      tick();
      audioCleanup.current = () => {
        cancelAnimationFrame(raf);
        stream.getTracks().forEach((tr) => tr.stop());
        void ctx.close();
      };
    } catch {
      // 마이크 거부 시 꿈틀 없이 인식만 진행
    }
  }, []);

  const speak = useCallback((text: string) => {
    setResponse(text);
    if (!("speechSynthesis" in window)) {
      setState("idle");
      return;
    }
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "ko-KR";
    utter.onstart = () => setState("speaking");
    utter.onend = () => setState("idle");
    utter.onerror = () => setState("idle");
    speechSynthesis.cancel();
    speechSynthesis.speak(utter);
  }, []);

  const handleCommand = useCallback(
    (text: string) => {
      setTranscript(text);
      setState("thinking");
      // 살짝 텀을 줘서 thinking 상태가 보이게
      setTimeout(() => {
        const result = runCommand(text);
        if (result) {
          speak(result);
        } else {
          setState("error");
          setResponse(HELP_TEXT);
          setTimeout(() => setState("idle"), 900);
        }
      }, 250);
    },
    [speak],
  );

  const startListening = useCallback(() => {
    const rec = createRecognition();
    if (!rec) return;
    recRef.current?.abort();
    recRef.current = rec;
    rec.onresult = (e) => {
      const text = e.results[0]?.[0]?.transcript ?? "";
      stopAudioMeter();
      handleCommand(text);
    };
    rec.onerror = () => {
      stopAudioMeter();
      setState("error");
      setResponse("잘 못 들었어요. 다시 말해주시거나 아래 버튼을 눌러주세요.");
      setTimeout(() => setState("idle"), 900);
    };
    rec.onend = () => {
      stopAudioMeter();
      setState((s) => (s === "listening" ? "idle" : s));
    };
    setState("listening");
    void startAudioMeter();
    rec.start();
  }, [handleCommand, startAudioMeter, stopAudioMeter]);

  const stopListening = useCallback(() => {
    recRef.current?.stop();
    stopAudioMeter();
    setState("idle");
  }, [stopAudioMeter]);

  const openWindow = useCallback(() => {
    setWindowPos((pos) => (pos ? clampWindowPosition(pos) : defaultWindowPosition()));
    setOpen(true);
  }, []);

  const collapseWindow = useCallback(() => {
    setOpen(false);
  }, []);

  const startDrag = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      if ((e.target as HTMLElement).closest("[data-no-drag]")) return;
      if (!windowPos) return;
      dragRef.current = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        startLeft: windowPos.left,
        startTop: windowPos.top,
      };
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [windowPos],
  );

  const moveDrag = useCallback((e: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    setWindowPos(
      clampWindowPosition({
        left: drag.startLeft + e.clientX - drag.startX,
        top: drag.startTop + e.clientY - drag.startY,
      }),
    );
  }, []);

  const endDrag = useCallback((e: React.PointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    dragRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  }, []);

  // 언마운트/닫힘 정리
  useEffect(() => {
    if (!open) {
      recRef.current?.abort();
      stopAudioMeter();
      if ("speechSynthesis" in window) speechSynthesis.cancel();
      setState("idle");
    }
  }, [open, stopAudioMeter]);

  useEffect(() => {
    function onResize() {
      setWindowPos((pos) => (pos ? clampWindowPosition(pos) : pos));
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (sheetMode && focus !== null) setOpen(false);
  }, [focus, sheetMode]);

  if (sheetMode && focus !== null) return null;

  const blobStateCls =
    state === "listening" ? "listening" : state === "thinking" ? "thinking" : "";
  const wrapCls =
    state === "error"
      ? "mugyeol-shaking"
      : state === "listening"
        ? ""
        : "mugyeol-breathing";

  return (
    <>
      {/* FAB */}
      <AnimatePresence>
        {!open && (
          <motion.button
            layoutId="mugyeol-window"
            onClick={openWindow}
            aria-label="무결이 열기"
            className="fixed bottom-32 right-4 z-30 flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-surface-2/80 backdrop-blur-md"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{
              delay: bootPopDone ? 0 : 1.2,
              type: "spring",
              stiffness: 300,
              damping: 20,
            }}
            onAnimationComplete={() => {
              bootPopDone = true;
            }}
            whileHover={{ scale: 1.08 }}
            whileTap={{ scale: 0.94 }}
          >
            <div className="mugyeol-breathing h-9 w-9">
              <div className="mugyeol-blob h-full w-full" />
            </div>
          </motion.button>
        )}
      </AnimatePresence>

      {/* 미니 창 */}
      <AnimatePresence>
        {open && (
          <motion.div
            layoutId="mugyeol-window"
            transition={{ type: "spring", stiffness: 350, damping: 30 }}
            className="fixed z-30 w-80"
            style={{
              left: windowPos?.left ?? `calc(100vw - ${WINDOW_W + WINDOW_MARGIN}px)`,
              top: windowPos?.top ?? `calc(100vh - ${WINDOW_H + WINDOW_BOTTOM}px)`,
            }}
          >
            <div
              className="hud-clip p-px"
              style={{
                background:
                  "linear-gradient(135deg, var(--mugyeol-a), var(--mugyeol-b), var(--mugyeol-c))",
              }}
            >
              <div className="hud-clip flex flex-col gap-3 bg-surface-1/95 p-4 backdrop-blur-md">
                <div
                  className="flex cursor-grab select-none items-center justify-between active:cursor-grabbing"
                  onPointerDown={startDrag}
                  onPointerMove={moveDrag}
                  onPointerUp={endDrag}
                  onPointerCancel={endDrag}
                  onDoubleClick={collapseWindow}
                  onClick={(e) => {
                    if (e.detail >= 2) collapseWindow();
                  }}
                  title="Drag to move. Double-click to collapse."
                >
                  <h2 className="font-display text-[11px] font-semibold uppercase tracking-[0.14em] text-text-hi">
                    무결이
                    <span className="ml-2 font-mono text-[9px] normal-case tracking-normal text-text-low">
                      integrity assistant
                    </span>
                  </h2>
                  <button
                    data-no-drag
                    onClick={collapseWindow}
                    aria-label="무결이 닫기"
                    className="text-text-low transition-colors hover:text-text-hi"
                  >
                    <X size={14} />
                  </button>
                </div>

                {/* 블롭 */}
                <div className="flex justify-center py-1">
                  <div ref={blobWrapRef} className={`h-24 w-24 ${wrapCls}`}>
                    <button
                      onClick={
                        speechSupported.current
                          ? state === "listening"
                            ? stopListening
                            : startListening
                          : undefined
                      }
                      aria-label={
                        speechSupported.current
                          ? state === "listening"
                            ? "듣기 중지"
                            : "말하기 시작"
                          : "음성 미지원"
                      }
                      className={`mugyeol-blob h-full w-full ${blobStateCls} ${
                        speechSupported.current ? "cursor-pointer" : "cursor-default"
                      }`}
                    />
                  </div>
                </div>

                <p className="text-center font-mono text-[10px] uppercase tracking-[0.14em] text-text-low" role="status">
                  {state === "listening"
                    ? "듣는 중..."
                    : state === "thinking"
                      ? "생각 중..."
                      : state === "speaking"
                        ? "말하는 중..."
                        : state === "error"
                          ? "인식 실패"
                          : speechSupported.current
                            ? "블롭을 누르고 말하세요"
                            : "이 브라우저는 음성 미지원"}
                </p>

                {transcript && (
                  <p className="border-l-2 border-hud pl-2 text-xs text-text-mid">"{transcript}"</p>
                )}
                <p className="text-xs leading-relaxed text-text-hi">{response}</p>

                {/* 빠른 명령 */}
                <div className="flex flex-wrap gap-1.5">
                  {QUICK_COMMANDS.map((c) => (
                    <button
                      key={c}
                      onClick={() => handleCommand(c)}
                      className="rounded-md border border-hud px-2 py-1 text-[11px] text-text-mid transition-colors hover:border-hud-active hover:text-text-hi active:scale-[0.97]"
                    >
                      {c}
                    </button>
                  ))}
                </div>

                {/* 텍스트 폴백 입력 */}
                <form
                  className="flex gap-1.5"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (textInput.trim()) {
                      handleCommand(textInput);
                      setTextInput("");
                    }
                  }}
                >
                  <input
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    placeholder="명령 입력"
                    aria-label="무결이 명령 입력"
                    className="min-w-0 flex-1 rounded-md border border-hud bg-surface-0 px-2 py-1.5 text-xs text-text-hi placeholder:text-text-low focus:border-hud-active focus:outline-none"
                  />
                  <button
                    type="submit"
                    aria-label="명령 전송"
                    className="flex w-8 items-center justify-center rounded-md border border-hud text-text-mid transition-colors hover:border-hud-active hover:text-text-hi"
                  >
                    <PaperPlaneRight size={13} />
                  </button>
                  {speechSupported.current && (
                    <button
                      type="button"
                      onClick={state === "listening" ? stopListening : startListening}
                      aria-label={state === "listening" ? "듣기 중지" : "음성 인식 시작"}
                      className={`flex w-8 items-center justify-center rounded-md border transition-colors ${
                        state === "listening"
                          ? "border-red-ops text-red-ops"
                          : "border-hud text-text-mid hover:border-hud-active hover:text-text-hi"
                      }`}
                    >
                      <Microphone size={13} weight={state === "listening" ? "fill" : "regular"} />
                    </button>
                  )}
                </form>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
