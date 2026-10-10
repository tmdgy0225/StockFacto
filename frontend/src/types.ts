export type Mode = "harness" | "control";
export type AgentName = "mock" | "claude";

export interface CaseSummary {
  id: string;
  title: string;
  symbol: string;
  request: string;
  tags: string[];
}

export interface Violation {
  rule_id: string;
  stage: string;
  message: string;
  line: number | null;
  fix_hint: string;
}

export interface Metrics {
  bars: number;
  trades: number;
  stop_hits: number;
  rejected_orders: number;
  max_weight_used: number;
  mdd: number;
  total_return: number;
}

export interface Attempt {
  n: number;
  code: string;
  diff: string;
  violations: Violation[];
  passed: boolean;
  metrics: Metrics | null;
  equity_curve: number[];
  stage_ms: Record<string, number>;
  tokens: { input: number; output: number };
}

export interface Fact {
  type: string;
  amount_krw: number | null;
  counterparty: string | null;
  source: string;
  status: "VERIFIED" | "UNVERIFIED";
  evidence: { report_nm: string; rcept_no: string; rcept_dt: string } | null;
}

export interface Trace {
  run_id: string;
  case_id: string;
  case_title: string;
  mode: Mode;
  agent: string;
  status: "RUNNING" | "PASSED" | "ESCALATED" | "RELEASED" | "ERROR";
  unsafe: boolean | null;
  context: {
    fact_status: "VERIFIED" | "UNVERIFIED";
    max_weight: number;
    facts: Fact[];
    tokens: { raw: number; compact: number; reduction: number };
  };
  plan: { max_weight: number; max_mdd: number; conflicts: string[]; scope: string } | null;
  attempts: Attempt[];
  escalation_reason: string | null;
  approval: "PENDING" | "APPROVED" | "REJECTED" | null;
  duration_ms: number;
}

export type StageName = "collect" | "context" | "plan" | "execute" | "lint" | "sandbox" | "gate" | "heal" | "handoff";

export type HarnessEvent =
  | { type: "stage"; stage: StageName; status: "running" | "done" | "pass" | "fail" | "skip"; attempt: number | null; detail: Record<string, unknown> }
  | { type: "attempt"; attempt: Attempt }
  | { type: "done"; trace: Trace }
  | { type: "error"; message: string };

export interface EvalReport {
  summary: {
    agent: string;
    cases: number;
    control: { unsafe_release_rate: number; human_review_runs: number; avg_prompt_tokens: number };
    harness: {
      unsafe_release_rate: number;
      passed: number;
      escalated: number;
      self_healing_rate: number | null;
      avg_attempts: number;
      human_review_runs: number;
      avg_prompt_tokens_first_attempt: number;
    };
    token_reduction: number | null;
  };
  rows: {
    case_id: string;
    title: string;
    fact_status: string;
    control_unsafe: boolean;
    control_rules: string[];
    control_mdd: number | null;
    harness_status: string;
    harness_attempts: number;
    harness_rules_seen: string[][];
    harness_mdd: number | null;
  }[];
}
