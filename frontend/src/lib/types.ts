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

// ---------------------------------------------------------------------------------------------------------------
// Findings (Day 7). Mirrors backend/apps/analysis/serializers.py (RiskFindingSerializer, EvidenceItemSerializer).
// ---------------------------------------------------------------------------------------------------------------
export interface DrugRef {
  id: number;
  generic_name: string;
}

/** One source behind a finding. `available: false` = the record was removed by a data reload; the UI says so instead of hiding it. */
export interface EvidenceItem {
  type: string; // "interaction" | "chunk"
  id: number | null;
  source: string;
  label: string;
  section: string;
  source_ref: string;
  license_note: string;
  url: string;
  available: boolean;
}

/** A confidence value never travels without its basis (rule.md §5). */
export interface ConfidenceBasis {
  verification_status: VerificationStatus;
  evidence_count: number;
  sources: string[];
}

export interface RiskFinding {
  id: number;
  drug_a: DrugRef;
  drug_b: DrugRef;
  /** Names as the person entered them (brand / raw text), keyed by drug on the server. The UI shows generic + the name as entered. */
  entered_names_a: string[];
  entered_names_b: string[];
  severity: Severity;
  rationale: string;
  confidence: number; // 0..1
  confidence_basis: ConfidenceBasis;
  verification_status: VerificationStatus;
  evidence: EvidenceItem[]; // never empty for a severity other than "unknown"
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
   * Day 9 backend fields. The Patients screen and the consent banner show them only when the server sends them:
   * nothing is guessed or faked in the UI.
   *  - consents: every consent record of the patient (active and withdrawn): the banner shows one row per type.
   *  - consent_active: one overall flag, used when `consents` is not sent.
   *  - medication_count: number of medicines on the record.
   */
  consent_active?: boolean;
  medication_count?: number;
  consents?: ConsentRecord[];
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
// Analysis runs (Day 6 + Day 7). Mirrors backend/apps/analysis (AnalysisStartSerializer, AnalysisDetailSerializer, AgentTrace).
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

/** What was analysed, exactly as frozen at run time (already PII-redacted). Frequency is left out on purpose. */
export interface SnapshotMedication {
  medication_id: number | null;
  raw_text: string;
  brand_name: string;
  strength: string;
  generic_name: string | null;
  resolution_status: string;
  source: string;
}

/** A medicine the pipeline could not resolve: shown as "not checked", never hidden. */
export interface AnalysisGap {
  medication_id: number;
  raw_text: string;
  brand_name: string;
  reason: string; // "needs_user_selection"
}

export interface DoctorSummary {
  doctor_summary_en: string;
  doctor_summary_bn: string;
  disclaimer_version: string;
}

export interface DisclaimerText {
  version: string;
  text_en: string;
  text_bn: string;
}

/**
 * GET /api/analysis/{id}/ — one shape for polling AND for the finished result.
 * While the run is queued / running / failed every clinical field is null or absent (a partial run never looks final).
 * The optional fields below are filled only when `status === "completed"`.
 */
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

  is_final?: boolean;
  disclaimer?: DisclaimerText;
  medications?: SnapshotMedication[] | null;
  findings?: RiskFinding[] | null;
  summary?: DoctorSummary | null;
  gaps?: AnalysisGap[] | null;
  /** Names of guardrail checks that replaced or changed some text. Shown to the doctor, never hidden. */
  guardrail_violations?: string[] | null;
}

/**
 * One row of GET /api/analysis/{id}/trace/ (`traces`). The stepper only needs the first three fields;
 * the summaries and tool calls feed the Agent trace tab. All of them are redacted on the server.
 */
export interface AgentTraceStep {
  agent_name: string;
  step_order: number;
  latency_ms: number;
  input_summary?: string;
  output_summary?: string;
  /** MCP / internal tool calls. Each is an object with at least a `tool` name; the rest of its shape varies by agent. */
  tool_calls?: unknown[];
}
// ---------------------------------------------------------------------------------------------------------------
// Consent (Day 9). Mirrors backend/apps/patients/models.py (Consent) and POST /api/patients/{id}/consents/.
// ---------------------------------------------------------------------------------------------------------------
export type ConsentScope = "analysis" | "family_view" | "retain_images";

export interface ConsentRecord {
  id: number;
  /** One of ConsentScope; kept as a string so an unknown value from the server cannot crash the screen. */
  scope: string;
  /** Who gave the consent (the patient or a guardian). A role such as "Patient", not a full name. */
  granted_by: string;
  granted_at: string;
  /** Set once the consent is withdrawn. A consent with `revoked_at` is no longer active. */
  revoked_at: string | null;
}

// ---------------------------------------------------------------------------------------------------------------
// Patient card (Day 9). GET /api/analysis/{id}/patient-card/ — already parsed by lib/patientCard.ts.
// ---------------------------------------------------------------------------------------------------------------
/** Plain-language summary for the patient or a caregiver. Never carries dosing or start/stop instructions. */
export interface PatientCard {
  run_id: number | null;
  /** "" when the server did not send that language. At least one of the two is non-empty. */
  text_bn: string;
  text_en: string;
  disclaimer_version: string;
  generated_at: string | null;
}

// ---------------------------------------------------------------------------------------------------------------
// Family view (Day 9, NRB). GET /api/family/patients/ and /api/family/patients/{id}/summary/ — parsed by lib/family.ts.
// ---------------------------------------------------------------------------------------------------------------
/** One patient shared with the signed-in family user (active family_view consent + active family link). */
export interface FamilyPatient {
  id: number;
  patient_code: string;
  relationship: string;
}

export interface FamilySummary {
  patient_id: number;
  patient_code: string;
  relationship: string;
  /** Highest severity among the findings of the latest analysis; null = no analysis has been shared yet. */
  severity: Severity | null;
  text_bn: string;
  text_en: string;
  /** Generic names only: no strength, no frequency. */
  medicines: string[];
  updated_at: string | null;
  consent_granted_by: string;
  disclaimer_version: string;
}