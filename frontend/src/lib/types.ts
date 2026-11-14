// Keep in sync with the backend OpenAPI schema (/api/schema/). TODO: generate from the schema.
export type Severity = "major" | "moderate" | "minor" | "unknown";
export type VerificationStatus = "verified" | "unverified" | "conflict";
export type Role = "doctor" | "pharmacist" | "family" | "admin";

export interface User {
  id: number;
  email: string;
  role: Role;
  display_name: string;
  preferred_language: string;
}

export interface EvidenceRef {
  type: "interaction" | "chunk";
  id: number;
  source: string;
}

export interface RiskFinding {
  id: number;
  drug_a: string;
  drug_b: string;
  severity: Severity;
  rationale: string;
  confidence: number;
  verification_status: VerificationStatus;
  evidence: EvidenceRef[]; // required for any severity other than "unknown"
}

export interface ApiError {
  error: { code: string; message: string; details?: unknown };
}

export type Sex = "male" | "female" | "other";
export type ResolutionStatus = "unresolved" | "resolved" | "user_confirmed";

export interface Patient {
  id: number;
  patient_code: string;
  birth_year: number | null;
  sex: string;
  weight_kg: string | null;
  created_at: string;
  /**
   * NOT returned by the API yet (consent and medicine counts arrive with the Day 9 backend work).
   * The Patients screen shows the consent badge / medicine count only when the server sends these
   * fields: nothing is guessed or faked in the UI.
   */
  consent_active?: boolean;
  medication_count?: number;
}

export interface PatientInput {
  birth_year?: number;
  sex?: Sex;
  weight_kg?: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Medication {
  id: number;
  raw_text: string;
  brand_name: string;
  generic_name: string | null;
  strength: string;
  frequency: string;
  resolution_status: ResolutionStatus;
  created_at: string;
}

export interface MedicationInput {
  raw_text: string;
  brand_name: string;
  strength: string;
  frequency: string;
  drug_id: number | null;
}

/** One row of GET /api/drugs/ (used only to turn a resolved generic name into the `drug_id` that POST medications needs). */
export interface DrugRecord {
  id: number;
  generic_name: string;
  aliases: string[];
}

// ---------------------------------------------------------------------------------------------------------------
// Analysis runs (Day 6). Mirrors backend/apps/analysis (AnalysisStartSerializer, AnalysisStatusSerializer, AgentTrace).
// ---------------------------------------------------------------------------------------------------------------
export type RunStatus = "queued" | "running" | "completed" | "failed";

/** The five pipeline steps, in the order the LangGraph pipeline runs them (backend-design.md §6.1). */
export type PipelineAgent = "resolver" | "clinical_notes" | "drug_interaction" | "advisory" | "verifier";

/** POST /api/analysis/ body. `idempotency_key` is generated once per click and re-sent on every retry of that click. */
export interface AnalysisStartRequest {
  patient_id: number;
  medication_ids: number[];
  idempotency_key: string;
}

/** 202 = new run queued · 200 = same idempotency key re-sent, the existing run is returned. */
export interface AnalysisStartResponse {
  run_id: number;
  status: RunStatus;
  idempotent_replay: boolean;
  disclaimer_version: string;
}

/** GET /api/analysis/{id}/ — status for polling. `findings_count` is null until the run is completed. */
export interface AnalysisRunStatus {
  run_id: number;
  patient_id: number;
  status: RunStatus;
  started_at: string | null;
  finished_at: string | null;
  medication_count: number;
  findings_count: number | null;
  /** Set only when status is "failed": timeout · pipeline_unavailable · malformed_finding · pipeline_error · enqueue_failed. */
  error_code: string | null;
  disclaimer_version: string;
}

/** One row of GET /api/analysis/{id}/trace/. Only the fields the stepper needs; summaries are for the Day 7 trace tab. */
export interface AgentTraceStep {
  agent_name: string;
  step_order: number;
  latency_ms: number;
}