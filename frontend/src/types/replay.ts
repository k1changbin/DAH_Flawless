/**
 * combat_replay.json (schema: dah_frontend_combat_log_v1) 타입 정의.
 * 실물 JSON에서 역추출. 백엔드 스키마를 절대 수정하지 않고 소비만 한다.
 */

export type WinnerSide = "BLUE" | "RED" | "DRAW";

export type RedAction =
  | "ABORT"
  | "FINALIZE_ATTACK"
  | "PROBE_BOUNDARY"
  | "SLOW_DRIFT"
  | "SWITCH_TACTIC"
  | "WAIT";

export type BlueAction = "DEFEND" | "INSPECT_INTERNAL" | "RAISE_SUSPICION" | "WAIT";

export type StepPhase =
  | "adapt"
  | "defense"
  | "finalize"
  | "idle"
  | "monitor"
  | "mutation"
  | "probe";

export type ZtaDomain = "command" | "telemetry" | "mission";

/** ZTA 결정. 데이터에서 관측된 값 + 게이트 설계상 존재 가능한 값 */
export type ZtaDecision =
  | "ALLOW"
  | "ALLOW_WITH_MONITOR"
  | "REVALIDATE"
  | "DEGRADE"
  | "QUARANTINE"
  | "DENY"
  | (string & {});

export interface ZtaStepDecision {
  domain: ZtaDomain;
  decision: ZtaDecision;
  trust_score: number;
  restrictive: boolean;
  allowed_use: string;
  reasons: string[];
}

/** R2+에서 확인된 실물: 객체 배열. 초기 라운드는 빈 배열. */
export interface DefenseAction {
  action: string;
  cost: number;
  status: string;
  target: string;
}

export interface StepBudgets {
  blue_compute_budget: number;
  blue_defense_steps: number;
  blue_power_budget: number;
  blue_round_defense_cost: number;
  red_budget: number;
  red_finalize_attempts: number;
  red_last_action_cost: number;
  red_mutation_steps: number;
  red_retry_attempts: number;
  red_round_attack_cost: number;
}

export interface TimelineStep {
  step: number;
  phase: StepPhase;
  red_action: RedAction;
  blue_action: BlueAction;
  detected: boolean;
  suspicion: number;
  defense_actions: Array<DefenseAction | string>;
  changed_path_count: number;
  changed_paths: string[];
  /** WAIT 등 일부 스텝에서 null (실데이터 검증됨) */
  delta: { applied: Record<string, number> | null; requested: Record<string, number> | null } | null;
  budgets: StepBudgets;
  score: Record<string, unknown>;
  zta: ZtaStepDecision[];
  observe_policy: Record<string, unknown>;
}

export interface RoundAttack {
  name: string;
  tactic: string;
  target_domain: ZtaDomain;
}

export interface RoundOutcome {
  winner: string;
  winner_side: WinnerSide;
  winner_detail: string;
  attack_success: boolean;
  detection_success: boolean;
  recovery_success: boolean | null;
  goal_id: string;
  goal_success: boolean;
  goal_reward: number;
  availability: number;
  mission_impact_score: number;
  containment_level: string | null;
  containment_score: number | null;
  reason: string;
  termination_reason: string | null;
}

export interface ZtaDomainVerdict {
  correct: boolean;
  decision: ZtaDecision;
  expected_restricted: boolean;
  restricted: boolean;
  trust_score: number;
}

export interface RoundZtaPolicy {
  attack_target_domain: ZtaDomain;
  decision_counts: Record<string, number>;
  informational_availability_cost: number;
  per_domain: Record<ZtaDomain, ZtaDomainVerdict>;
}

export interface RoundHighlight {
  type: string;
  step: number | null;
  message: string;
}

export interface ActionRun {
  action: string;
  from_step: number;
  to_step: number;
  count: number;
}

export interface ReplayRound {
  round: number;
  scenario?: string;
  scenario_profile?: Record<string, unknown>;
  title: string;
  attack: RoundAttack;
  outcome: RoundOutcome;
  goal: Record<string, unknown>;
  timeline: TimelineStep[];
  step_count: number;
  highlights: RoundHighlight[];
  action_runs: ActionRun[];
  zta_policy: RoundZtaPolicy;
  observe_policy: Record<string, unknown>;
  availability_recovery: Record<string, unknown> | null;
}

export interface ZeroTrustSummary {
  avg_policy_decision_correctness: number;
  decision_counts: Record<string, number>;
  per_round: Array<{
    attack_target_domain: ZtaDomain;
    per_domain: Record<ZtaDomain, ZtaDomainVerdict>;
  }>;
}

export interface CombatReplay {
  schema: string;
  log_type: string;
  source: Record<string, unknown>;
  filters: Record<string, unknown>;
  policy_snapshot: Record<string, unknown> | null;
  summary: Record<string, unknown>;
  zero_trust: ZeroTrustSummary;
  rounds: ReplayRound[];
}
