import { api } from "./api";

/** A rate as the backend computes it: k of n, the value (null = not measurable) and a 95% Wilson interval. */
export interface EvalRate {
  k: number;
  n: number;
  value: number | null;
  ci95: [number, number] | null;
}

export type CaseOutcome = "match" | "missed" | "false_alarm" | "severity_mismatch";

export interface EvalCaseResult {
  drug_a: string;
  drug_b: string;
  expected: string;
  predicted: string;
  pair_status: string;
  outcome: CaseOutcome;
  passed: boolean;
}

export interface EvalSplitBlock {
  run_id: number;
  split: "dev" | "test";
  finished_at: string | null;
  n_cases: number;
  fingerprint: string;
  positives: number;
  negatives: number;
  recall: EvalRate | null;
  precision: EvalRate | null;
  /** False when the set has no reviewer-labelled negatives: precision must then be shown as "not measurable". */
  precision_measurable: boolean;
  severity_agreement: EvalRate | null;
  major_not_called_major: EvalRate | null;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  undercalled: number;
  overcalled: number;
  missed_by_reason: Record<string, number>;
  guardrail: { checked: number; violations: number; pass_rate: EvalRate };
  reference_labels_from_source: number;
  caveats: string[];
  /** Dev split only. The test split never stores per-case rows. */
  cases: EvalCaseResult[] | null;
  cases_hidden: boolean;
  transports: string[];
}

export interface EvalHistoryRow {
  id: number;
  split: string;
  status: string;
  error_code: string;
  n_cases: number;
  recall: number | null;
  precision: number | null;
  severity_agreement: number | null;
  finished_at: string | null;
}

export interface EvalSetSplit {
  n: number;
  by_expected_severity: Record<string, number>;
  unreviewed: number;
}

export interface EvalDashboard {
  generated_at: string;
  pairs: { dev: EvalSplitBlock | null; test: EvalSplitBlock | null };
  set: { dev: EvalSetSplit; test: EvalSetSplit; warnings: string[] };
  guardrail_audit: {
    findings_total: number;
    findings_with_severity: number;
    severity_without_evidence: number;
    pass_rate: EvalRate;
  };
  history: EvalHistoryRow[];
}

/** GET /api/eval/dashboard/ — admin only. */
export const getEvalDashboard = (signal?: AbortSignal) => api<EvalDashboard>("/eval/dashboard/", { signal });

/** 0.7826 -> "78.3%". null -> "n/a". */
export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${(value * 100).toFixed(1)}%`;
}

/** "95% CI 61–90%" or "". */
export function ci(rate: EvalRate | null | undefined): string {
  if (!rate || !rate.ci95) return "";
  return `${Math.round(rate.ci95[0] * 100)}–${Math.round(rate.ci95[1] * 100)}%`;
}
