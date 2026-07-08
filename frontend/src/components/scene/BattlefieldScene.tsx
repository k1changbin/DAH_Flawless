import { useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Grid, Html, Line, OrbitControls } from "@react-three/drei";
import type { Group, Mesh, MeshBasicMaterial } from "three";
import { MathUtils } from "three";
import { getRound, getStep } from "../../data";
import { useReplayStore } from "../../store/useReplayStore";
import type { TimelineStep, ZtaDomain, ZtaStepDecision } from "../../types/replay";

/* 팔레트 (index.css 토큰과 동일 값) */
const C = {
  hud: "#2a3a5c",
  hudActive: "#5fd4f5",
  red: "#ff5d45",
  blue: "#4fa3ff",
  warn: "#f5c542",
  text: "#9fb0c9",
};

const C2_POS: [number, number, number] = [0, 0.45, 0];

interface AssetDef {
  id: string;
  domain: ZtaDomain;
  pos: [number, number, number];
  kind: "satcom" | "uav" | "ugv";
  /** 콜아웃 배치 (UGV는 우하단 EVENT LOG와 겹쳐서 위로) */
  callout: "right" | "top";
}

const ASSETS: AssetDef[] = [
  { id: "CMD LINK", domain: "command", pos: [0, 3.1, -1.6], kind: "satcom", callout: "right" },
  { id: "UAV", domain: "telemetry", pos: [-2.7, 1.7, 0.9], kind: "uav", callout: "right" },
  { id: "UGV", domain: "mission", pos: [2.5, 0.4, 1.7], kind: "ugv", callout: "top" },
];

const REDUCED_MOTION =
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** 현재 스텝에서 각 도메인 링크의 상태 */
function useLinkStates() {
  const roundIdx = useReplayStore((s) => s.roundIdx);
  const stepIdx = useReplayStore((s) => s.stepIdx);
  const round = getRound(roundIdx);
  const step = getStep(roundIdx, stepIdx);

  return useMemo(() => {
    const states: Record<ZtaDomain, { attack: boolean; restricted: boolean }> = {
      command: { attack: false, restricted: false },
      telemetry: { attack: false, restricted: false },
      mission: { attack: false, restricted: false },
    };
    if (!step) return { states, detected: false, step: null as TimelineStep | null };
    const attacking = step.red_action !== "WAIT" && step.red_action !== "ABORT";
    if (attacking) states[round.attack.target_domain].attack = true;
    for (const z of step.zta) {
      if (z.restrictive) states[z.domain].restricted = true;
    }
    return { states, detected: step.detected, step: step as TimelineStep | null };
  }, [round, step]);
}

/** e71 레퍼런스: 리더 라인으로 연결된 HUD 콜아웃 */
function NodeCallout({
  def,
  zta,
  attack,
  restricted,
}: {
  def: AssetDef;
  zta: ZtaStepDecision | undefined;
  attack: boolean;
  restricted: boolean;
}) {
  const status = attack ? "ATTACK" : restricted ? "RESTRICTED" : "NOMINAL";
  const statusCls = attack ? "text-red-ops" : restricted ? "text-warn" : "text-ok";
  const card = (
    <div className="hud-clip bg-hud-active p-px">
          <div className="hud-clip space-y-1.5 bg-surface-1/95 p-2.5 backdrop-blur-md">
            <div className="flex items-baseline justify-between">
              <span className={`font-display text-[11px] font-bold tracking-[0.1em] ${attack ? "text-red-ops" : "text-hud-active"}`}>
                {def.id}
              </span>
              <span className="font-mono text-[9px] uppercase text-text-low">{def.domain}</span>
            </div>
            <div className="flex justify-between font-mono text-[10px]">
              <span className="text-text-low">zta</span>
              <span className="text-text-mid">{zta?.decision ?? "--"}</span>
              <span className="text-text-hi">{zta ? zta.trust_score.toFixed(2) : "--"}</span>
            </div>
            <div className="flex justify-between font-mono text-[10px]">
              <span className="text-text-low">status</span>
              <span className={statusCls}>{status}</span>
            </div>
            {zta && zta.reasons.length > 0 && (
              <p className="truncate font-mono text-[9px] text-text-low">{zta.reasons[0]}</p>
            )}
          </div>
        </div>
  );

  if (def.callout === "top") {
    return (
      <Html position={[0, 0.95, 0]} center zIndexRange={[40, 0]} style={{ pointerEvents: "none" }}>
        <div className="callout-in flex flex-col items-center" style={{ transform: "translateY(-58%)" }}>
          <div style={{ width: 196 }}>{card}</div>
          <div className="h-5 w-px bg-hud-active" />
        </div>
      </Html>
    );
  }

  return (
    <Html position={[0.3, 0.5, 0]} zIndexRange={[40, 0]} style={{ pointerEvents: "none" }}>
      <div className="callout-in" style={{ transformOrigin: "left bottom" }}>
        <div
          className="h-px w-9 bg-hud-active"
          style={{ transform: "rotate(-30deg)", transformOrigin: "left center" }}
        />
        <div style={{ marginLeft: 32, marginTop: -6, width: 196 }}>{card}</div>
      </div>
    </Html>
  );
}

function AssetNode({
  def,
  underAttack,
  restricted,
  zta,
  hovered,
  onHover,
}: {
  def: AssetDef;
  underAttack: boolean;
  restricted: boolean;
  zta: ZtaStepDecision | undefined;
  hovered: boolean;
  onHover: (id: string | null) => void;
}) {
  const group = useRef<Group>(null);
  const phase = useMemo(() => Math.random() * Math.PI * 2, []);

  useFrame(({ clock }) => {
    if (!group.current || REDUCED_MOTION) return;
    // 공중 자산만 미세 부유
    if (def.kind !== "ugv") {
      group.current.position.y = def.pos[1] + Math.sin(clock.elapsedTime * 0.8 + phase) * 0.07;
    }
    if (def.kind === "satcom") group.current.rotation.y += 0.004;
  });

  const color = underAttack ? C.red : C.hudActive;
  const glowColor = underAttack ? C.red : restricted ? C.warn : C.hudActive;

  return (
    <group
      ref={group}
      position={def.pos}
      onPointerOver={(e) => {
        e.stopPropagation();
        onHover(def.id);
      }}
      onPointerOut={(e) => {
        e.stopPropagation();
        onHover(null);
      }}
    >
      {/* 호버 히트 영역 (보이지 않음) */}
      <mesh visible={false}>
        <sphereGeometry args={[0.6]} />
        <meshBasicMaterial />
      </mesh>
      {(underAttack || restricted || hovered) && (
        <mesh scale={underAttack ? 0.78 : 0.62}>
          <sphereGeometry args={[1, 20, 20]} />
          <meshBasicMaterial
            color={glowColor}
            transparent
            opacity={underAttack ? 0.16 : 0.09}
            depthWrite={false}
          />
        </mesh>
      )}
      {def.kind === "satcom" && (
        <mesh>
          <octahedronGeometry args={[0.34]} />
          <meshStandardMaterial color={color} wireframe />
        </mesh>
      )}
      {def.kind === "uav" && (
        <mesh rotation={[Math.PI, 0, 0]}>
          <coneGeometry args={[0.26, 0.5, 4]} />
          <meshStandardMaterial color={color} wireframe />
        </mesh>
      )}
      {def.kind === "ugv" && (
        <mesh>
          <boxGeometry args={[0.42, 0.26, 0.56]} />
          <meshStandardMaterial color={color} wireframe />
        </mesh>
      )}
      {/* 코어 발광점 */}
      <mesh scale={0.09}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshBasicMaterial color={underAttack ? C.red : C.hudActive} />
      </mesh>
      <Html center distanceFactor={11} style={{ pointerEvents: "none" }}>
        <div
          style={{
            fontFamily: "'JetBrains Mono Variable', monospace",
            fontSize: 10,
            letterSpacing: "0.12em",
            color: underAttack ? C.red : C.text,
            whiteSpace: "nowrap",
            transform: "translateY(-26px)",
          }}
        >
          {def.id}
        </div>
      </Html>
      {hovered && <NodeCallout def={def} zta={zta} attack={underAttack} restricted={restricted} />}
    </group>
  );
}

/** 통신 링크: 기본 라인 + 공격/제한 시 대시 흐름 */
function DomainLink({
  from,
  to,
  attack,
  restricted,
}: {
  from: [number, number, number];
  to: [number, number, number];
  attack: boolean;
  restricted: boolean;
}) {
  const dashRef = useRef<{ dashOffset: number } | null>(null);

  useFrame((_, delta) => {
    if (dashRef.current && attack && !REDUCED_MOTION) {
      // 공격 방향(자산→C2)으로 흐르는 대시
      dashRef.current.dashOffset -= delta * 1.6;
    }
  });

  const color = attack ? C.red : restricted ? C.warn : C.hud;

  return (
    <group>
      {/* 베이스 라인 */}
      {(attack || restricted) && (
        <Line
          points={[from, to]}
          color={color}
          lineWidth={attack ? 8 : 5}
          transparent
          opacity={attack ? 0.13 : 0.09}
        />
      )}
      <Line points={[from, to]} color={color} lineWidth={attack ? 1.5 : 1} transparent opacity={attack ? 0.5 : 0.35} />
      {/* 흐름 대시 (공격 시에만) */}
      {attack && (
        <Line
          points={[from, to]}
          color={C.red}
          lineWidth={2.5}
          dashed
          dashSize={0.22}
          gapSize={0.34}
          ref={(line) => {
            // drei Line ref → Line2, material에 dashOffset 존재
            if (line) dashRef.current = line.material as unknown as { dashOffset: number };
          }}
        />
      )}
    </group>
  );
}

/** 탐지 시 C2에서 퍼지는 링 펄스 */
function DetectionPulse({ active }: { active: boolean }) {
  const mesh = useRef<Mesh>(null);
  const t = useRef(0);

  useFrame((_, delta) => {
    if (!mesh.current) return;
    const mat = mesh.current.material as MeshBasicMaterial;
    if (!active || REDUCED_MOTION) {
      mat.opacity = active ? 0.5 : 0;
      mesh.current.scale.setScalar(active ? 1.4 : 0.001);
      return;
    }
    t.current = (t.current + delta * 0.7) % 1;
    const s = 0.5 + t.current * 2.2;
    mesh.current.scale.setScalar(s);
    mat.opacity = 0.7 * (1 - t.current);
  });

  return (
    <mesh ref={mesh} position={[C2_POS[0], 0.06, C2_POS[2]]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.9, 0.98, 48]} />
      <meshBasicMaterial color={C.blue} transparent opacity={0} />
    </mesh>
  );
}

/** 포커스 진영에 따라 씬이 살짝 기우는 리그 */
function SceneRig({ children }: { children: React.ReactNode }) {
  const group = useRef<Group>(null);
  const focus = useReplayStore((s) => s.focus);

  useFrame((_, delta) => {
    if (!group.current) return;
    const target = focus === "RED" ? 0.22 : focus === "BLUE" ? -0.22 : 0;
    group.current.rotation.y = REDUCED_MOTION
      ? target
      : MathUtils.damp(group.current.rotation.y, target, 2.2, delta);
  });

  return <group ref={group}>{children}</group>;
}

function SceneContent() {
  const { states, detected, step } = useLinkStates();
  const [hoverId, setHoverId] = useState<string | null>(null);

  useEffect(() => {
    document.body.style.cursor = hoverId ? "pointer" : "";
    return () => {
      document.body.style.cursor = "";
    };
  }, [hoverId]);

  return (
    <SceneRig>
      {/* 지형 그리드 (이미지 #6 무드) */}
      <Grid
        position={[0, 0, 0]}
        args={[24, 24]}
        cellSize={0.6}
        cellColor={C.hud}
        cellThickness={0.5}
        sectionSize={3}
        sectionColor={C.hud}
        sectionThickness={1}
        fadeDistance={17}
        fadeStrength={2.5}
      />

      {/* BLUE C2 코어 */}
      <group position={C2_POS}>
        <mesh>
          <icosahedronGeometry args={[0.4, 0]} />
          <meshStandardMaterial color={C.blue} wireframe />
        </mesh>
        <mesh scale={0.13}>
          <sphereGeometry args={[1, 12, 12]} />
          <meshBasicMaterial color={C.blue} />
        </mesh>
        <Html center distanceFactor={11} style={{ pointerEvents: "none" }}>
          <div
            style={{
              fontFamily: "'JetBrains Mono Variable', monospace",
              fontSize: 10,
              letterSpacing: "0.12em",
              color: C.blue,
              whiteSpace: "nowrap",
              transform: "translateY(-30px)",
            }}
          >
            BLUE C2
          </div>
        </Html>
      </group>

      {/* 자산 노드 + 링크 */}
      {ASSETS.map((a) => (
        <group key={a.id}>
          <AssetNode
            def={a}
            underAttack={states[a.domain].attack}
            restricted={states[a.domain].restricted}
            zta={step?.zta.find((z) => z.domain === a.domain)}
            hovered={hoverId === a.id}
            onHover={setHoverId}
          />
          <DomainLink
            from={a.pos}
            to={C2_POS}
            attack={states[a.domain].attack}
            restricted={states[a.domain].restricted}
          />
        </group>
      ))}

      <DetectionPulse active={detected} />

      <ambientLight intensity={0.7} />
      <directionalLight position={[4, 8, 5]} intensity={0.9} />
    </SceneRig>
  );
}

/** WebGL 불가 환경용 2.5D 폴백 */
function Fallback2D() {
  const { states, detected } = useLinkStates();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3">
      <p className="font-display text-xs font-semibold uppercase tracking-[0.2em] text-text-low">
        Topology (2D Fallback)
      </p>
      {ASSETS.map((a) => {
        const s = states[a.domain];
        const cls = s.attack ? "text-red-ops border-red-ops/50" : s.restricted ? "text-warn border-warn/50" : "text-text-mid border-hud";
        return (
          <div key={a.id} className={`flex w-64 items-center justify-between border px-3 py-2 font-mono text-xs ${cls}`}>
            <span>{a.id}</span>
            <span className="text-text-low">{a.domain}</span>
            <span>{s.attack ? "ATTACK" : s.restricted ? "RESTRICTED" : "NOMINAL"}</span>
          </div>
        );
      })}
      <p className={`font-mono text-xs ${detected ? "text-hud-active" : "text-text-low"}`}>
        {detected ? "DETECTED" : "MONITORING"}
      </p>
    </div>
  );
}

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function BattlefieldScene() {
  const [webgl] = useState(hasWebGL);

  if (!webgl) return <Fallback2D />;

  return (
    <Canvas
      dpr={[1, 1.5]}
      camera={{ position: [5.5, 4.6, 7.5], fov: 42 }}
      gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
      style={{ background: "transparent" }}
    >
      <SceneContent />
      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        enablePan={false}
        minDistance={5}
        maxDistance={14}
        minPolarAngle={0.5}
        maxPolarAngle={1.35}
        target={[0, 0.8, 0]}
      />
    </Canvas>
  );
}
