import type { MessageKey } from "../i18n";
import { api, ApiRequestError } from "./api";
import { normalizeVerification } from "./results";
import type {
  AnalysisGap,
  DrugRef,
  EvidenceItem,
  Severity,
  SeverityPicture,
  TwinBaseDrug,
  TwinComparison,
  TwinFinding,
  TwinNoRecordPair,
  TwinScenario,
  TwinScenarioSummary,
} from "./types";

// ---------------------------------------------------------------------------------------------------------------
// What-if (Digital Twin) API, Day 10. Backend: apps/twin (views.py, serializers.py, services.py).
//   POST /api/twin/                 {base_run_id, generic_name}  -> one scenario (201 new, 200 repeated request)
//   GET  /api/twin/{id}/            -> one stored scenario (a snapshot: never recalculated)
//   GET  /api/analysis/{id}/twin/   -> compact history of one analysis, newest first
// Everything below reads the answer defensively: a field that is missing or has an unexpected type becomes a safe
// default, never a crash and never a made-up value (an unknown severity is shown as "unknown", not as anything milder).
// ---------------------------------------------------------------------------------------------------------------

const SEVERITIES: readonly Severity[] = ["major", "moderate", "minor", "unknown"];

function obj(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}
function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
function arr(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function strings(value: unknown): string[] {
  return arr(value).filter((v): v is string => typeof v === "string");
}
function severity(value: unknown): Severity {
  return SEVERITIES.includes(value as Severity) ? (value as Severity) : "unknown";
}
/** null stays null ("no known severity"); anything else is read as a severity. */
function severityOrNull(value: unknown): Severity | null {
  return value === null || value === undefined ? null : severity(value);
}

function drugRef(value: unknown): DrugRef {
  const o = obj(value);
  return { id: num(o.id), generic_name: str(o.generic_name).trim() };
}

function evidenceItem(value: unknown): EvidenceItem {
  const o = obj(value);
  return {
    type: str(o.type),
    id: typeof o.id === "number" ? o.id : null,
    source: str(o.source),
    label: str(o.label),
    section: str(o.section),
    source_ref: str(o.source_ref),
    license_note: str(o.license_note),
    url: str(o.url),
    // Only an explicit `false` means "the record was removed by a data reload". A missing field is not treated as removed.
    available: o.available !== false,
    // Evidence panel fields (same names as the main analysis). A what-if source may come without a confidence.
    source_name: str(o.source_name),
    source_url: str(o.source_url),
    excerpt: str(o.excerpt),
    confidence: typeof o.confidence === "number" && Number.isFinite(o.confidence) ? o.confidence : null,
  };
}

function finding(value: unknown): TwinFinding {
  const o = obj(value);
  const evidence = arr(o.evidence).map(evidenceItem);
  const status = normalizeVerification(str(o.verification_status));
  const basis = obj(o.confidence_basis);
  return {
    drug_a: drugRef(o.drug_a),
    drug_b: drugRef(o.drug_b),
    entered_names_a: strings(o.entered_names_a),
    entered_names_b: strings(o.entered_names_b),
    severity: severity(o.severity),
    rationale: str(o.rationale),
    management: str(o.management).trim() || null,
    confidence: num(o.confidence),
    confidence_basis: {
      verification_status: normalizeVerification(str(basis.verification_status) || status),
      evidence_count: num(basis.evidence_count, evidence.length),
      sources: strings(basis.sources),
    },
    verification_status: status,
    evidence,
    pair_status: str(o.pair_status, "record"),
    severity_conflict: o.severity_conflict === true,
  };
}

function noRecordPair(value: unknown): TwinNoRecordPair {
  const o = obj(value);
  return {
    drug_a: drugRef(o.drug_a),
    drug_b: drugRef(o.drug_b),
    entered_names_a: strings(o.entered_names_a),
    entered_names_b: strings(o.entered_names_b),
  };
}

function baseDrug(value: unknown): TwinBaseDrug {
  const o = obj(value);
  return { ...drugRef(o), entered_names: strings(o.entered_names) };
}

function picture(value: unknown): SeverityPicture {
  const o = obj(value);
  const c = obj(o.counts);
  return {
    highest_severity: severityOrNull(o.highest_severity),
    counts: { major: num(c.major), moderate: num(c.moderate), minor: num(c.minor), unknown: num(c.unknown) },
    total: num(o.total),
  };
}

function comparison(value: unknown): TwinComparison {
  const o = obj(value);
  return {
    before: picture(o.before),
    after: picture(o.after),
    highest_severity_changed: o.highest_severity_changed === true,
    base_findings_count: num(o.base_findings_count),
    new_findings_count: num(o.new_findings_count),
    pairs_checked: num(o.pairs_checked),
  };
}

function gap(value: unknown): AnalysisGap {
  const o = obj(value);
  return {
    medication_id: num(o.medication_id),
    raw_text: str(o.raw_text),
    brand_name: str(o.brand_name),
    reason: str(o.reason),
  };
}

/** Returns null when the body is not a usable scenario (no id, or no name for the added medicine): the screen then says so. */
export function parseScenario(body: unknown): TwinScenario | null {
  const o = obj(body);
  const id = num(o.scenario_id);
  const drug = drugRef(o.hypothetical_drug);
  if (!Number.isInteger(id) || id <= 0 || !drug.generic_name) return null;

  const note = obj(o.simulation_note);
  return {
    scenario_id: id,
    base_run_id: num(o.base_run_id),
    patient_id: num(o.patient_id),
    created_at: str(o.created_at),
    simulation: o.simulation !== false,
    simulation_note: { text_en: str(note.text_en), text_bn: str(note.text_bn) },
    hypothetical_drug: drug,
    base_drugs: arr(o.base_drugs).map(baseDrug),
    added_findings: arr(o.added_findings).map(finding),
    no_record_pairs: arr(o.no_record_pairs).map(noRecordPair),
    comparison: comparison(o.comparison),
    gaps: arr(o.gaps).map(gap),
    limitations: strings(o.limitations),
    guardrail_violations: strings(o.guardrail_violations),
    disclaimer_version: str(o.disclaimer_version),
  };
}

export function parseSummary(value: unknown): TwinScenarioSummary | null {
  const o = obj(value);
  const id = num(o.scenario_id);
  const drug = drugRef(o.hypothetical_drug);
  if (!Number.isInteger(id) || id <= 0 || !drug.generic_name) return null;
  return {
    scenario_id: id,
    hypothetical_drug: drug,
    created_at: str(o.created_at),
    new_findings_count: num(o.new_findings_count),
    highest_severity_after: severityOrNull(o.highest_severity_after),
    highest_severity_changed: o.highest_severity_changed === true,
  };
}

/** The history row of a scenario that is already on screen (used right after a run, so the list needs no extra request). */
export function summaryOf(s: TwinScenario): TwinScenarioSummary {
  return {
    scenario_id: s.scenario_id,
    hypothetical_drug: s.hypothetical_drug,
    created_at: s.created_at,
    new_findings_count: s.comparison.new_findings_count,
    highest_severity_after: s.comparison.after.highest_severity,
    highest_severity_changed: s.comparison.highest_severity_changed,
  };
}

/** A 2xx answer that cannot be used is treated like a server failure, so the person sees an error and not an empty result. */
function unusable(): ApiRequestError {
  return new ApiRequestError(502, null);
}

/** Add one hypothetical medicine (by generic name) to a completed analysis. Nothing is saved to the patient's record. */
export async function runTwin(baseRunId: number, genericName: string, signal?: AbortSignal): Promise<TwinScenario> {
  const body = await api<unknown>("/twin/", {
    method: "POST",
    body: JSON.stringify({ base_run_id: baseRunId, generic_name: genericName }),
    signal,
  });
  const scenario = parseScenario(body);
  if (!scenario) throw unusable();
  return scenario;
}

export async function getTwinScenario(id: number, signal?: AbortSignal): Promise<TwinScenario> {
  const scenario = parseScenario(await api<unknown>(`/twin/${id}/`, { signal }));
  if (!scenario) throw unusable();
  return scenario;
}

export async function listTwinScenarios(runId: number, signal?: AbortSignal): Promise<TwinScenarioSummary[]> {
  const body = obj(await api<unknown>(`/analysis/${runId}/twin/`, { signal }));
  return arr(body.results)
    .map(parseSummary)
    .filter((s): s is TwinScenarioSummary => s !== null);
}

const CODE_KEY: Partial<Record<string, MessageKey>> = {
  drug_not_found: "twin.error.drug_not_found",
  drug_already_in_run: "twin.error.drug_already_in_run",
  base_run_has_no_drugs: "twin.error.base_run_has_no_drugs",
  base_run_not_completed: "twin.error.base_run_not_completed",
  throttled: "twin.error.tooMany",
  not_found: "twin.error.notFound",
};

/** The message for a failed what-if call. The server's machine `code` decides, never its English `message`. */
export function twinErrorKey(err: unknown): MessageKey {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) return "twin.error.network";
    const byCode = CODE_KEY[err.body?.error?.code ?? ""];
    if (byCode) return byCode;
    if (err.status === 429) return "twin.error.tooMany";
    if (err.status === 404) return "twin.error.notFound";
  }
  return "twin.error.generic";
}

/** Limitation codes the server may send, mapped to the sentence shown for each. An unknown code gets a neutral sentence. */
export const LIMITATION_KEY: Partial<Record<string, MessageKey>> = {
  interaction_table_only: "twin.limit.interaction_table_only",
  labs_vitals_not_used: "twin.limit.labs_vitals_not_used",
  label_passages_not_searched: "twin.limit.label_passages_not_searched",
  unresolved_medications_not_checked: "twin.limit.unresolved_medications_not_checked",
};