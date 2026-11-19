// Keep in sync with the backend OpenAPI schema (/api/schema/). TODO: generate from the schema.
export type Severity = "major" | "moderate" | "minor" | "unknown";
export type VerificationStatus = "verified" | "unverified" | "conflict";
export type Role = "doctor" | "pharmacist" | "family" | "admin";

export type DashboardActivityType =
  | "analysis_run"
  | "patient_opened"
  | "family_viewed"
  | "consent_granted"
  | "consent_revoked"
  | "consent_changed";

export interface DashboardSummary {
  total_patients: number;
  total_analyses: number;
  pending_reviews: number;
  pending_followups: number;
  overdue_followups: number;
  recent_patients: Array<{
    id: number;
    patient_code: string;
    medication_count: number;
  }>;
  recent_activity: Array<{
    id: number;
    event: DashboardActivityType;
    patient_code: string;
    at: string;
  }>;
}

export type FollowUpTaskType =
  | "review_analysis"
  | "patient_contact"
  | "medication_reconciliation"
  | "follow_up_visit";
export type FollowUpTaskStatus = "to_review" | "in_progress" | "done";

export interface FollowUpTask {
  id: number;
  patient_id: number;
  patient_code: string;
  analysis_run_id: number | null;
  task_type: FollowUpTaskType;
  status: FollowUpTaskStatus;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface FollowUpTaskCreate {
  patient_id: number;
  analysis_run_id: number | null;
  task_type: FollowUpTaskType;
  due_date: string | null;
}

export type FollowUpTaskUpdate = Partial<Pick<FollowUpTask, "status" | "due_date">>;

export type NotificationEvent = "scan_ready" | "scan_failed" | "analysis_ready" | "analysis_failed";

export interface NotificationItem {
  id: number;
  event: NotificationEvent;
  scan_id: number | null;
  analysis_run_id: number | null;
  patient_id: number | null;
  created_at: string;
  read_at: string | null;
}

export interface NotificationList {
  unread_count: number;
  results: NotificationItem[];
}

export interface User {
  id: number;
  email: string;
  role: Role;
  display_name: string;
  preferred_language: string;
  /** False until the emailed link was opened. */
  email_verified?: boolean;
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
  /** Human name of the source, e.g. "DDInter 2.0". */
  source_name: string;
  /** Link to the source ("" when none is known). Render it only through safeHttpUrl(). */
  source_url: string;
  /** Short verbatim quote of the stored source text. "" when none may be shown (or the record is gone). */
  excerpt: string;
  /** 0..1, the confidence of the finding this source belongs to (not a per-source score). null = not sent. */
  confidence: number | null;
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
  /** Optional display name; "" when none was entered. Older server responses may omit it. */
  name?: string;
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

export interface PatientAnalysisHistoryRun {
  run_id: number;
  occurred_at: string | null;
  medication_count: number;
  findings_count: number;
  severity_counts: Record<Severity, number>;
  verification_counts: Record<VerificationStatus, number>;
}

export interface PatientAnalysisHistory {
  total_count: number;
  results: PatientAnalysisHistoryRun[];
}

export interface PatientInput {
  name?: string;
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

/** One row of GET /api/analysis/runs/ (metadata only; the clinical result is read from /analysis/{id}/). */
export interface AnalysisListItem {
  run_id: number;
  patient_id: number;
  patient_code: string;
  status: RunStatus;
  medication_count: number;
  findings_count: number;
  started_at: string | null;
  finished_at: string | null;
}

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

export interface InteractionMapNode {
  id: string;
  label: string;
  state: "matched" | "not_checked";
  medication_count: number;
}

export interface InteractionMapEdge {
  finding_id: number;
  source_node_id: string;
  target_node_id: string;
  severity: Severity;
  verification_status: VerificationStatus;
  evidence_count: number;
}

export interface InteractionMap {
  nodes: InteractionMapNode[];
  edges: InteractionMapEdge[];
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
  interaction_map?: InteractionMap | null;
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

/** The six stories of the timeline, in order (backend/apps/analysis/results.py, trace_timeline). */
export type TimelineStageKey = "photo_upload" | "ocr" | "resolve" | "interaction" | "guardrail" | "report";

/** skipped = the stage did not apply (e.g. typed in by hand, so there was no image and no OCR). */
export type TimelineStatus = "done" | "running" | "failed" | "pending" | "skipped";

/**
 * One stage of GET /api/analysis/{id}/trace/ (`timeline`). Statuses are live; `duration_ms` is null until the run is
 * completed (and always null for upload / OCR, which are not timed). `meta` holds counts only — the UI words them.
 */
export interface TimelineStage {
  key: TimelineStageKey;
  status: TimelineStatus;
  duration_ms: number | null;
  meta: Record<string, number>;
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

// ---------------------------------------------------------------------------------------------------------------
// What-if / Digital Twin (Day 10). Mirrors backend/apps/twin/serializers.py. Always a SIMULATION, always labelled as one.
// POST /api/twin/ · GET /api/twin/{id}/ · GET /api/analysis/{id}/twin/ — parsed by lib/twin.ts.
// ---------------------------------------------------------------------------------------------------------------
/** What a finding card needs: every RiskFinding field except the database id (a what-if finding is not stored as one). */
export type FindingView = Omit<RiskFinding, "id">;

export interface TwinBaseDrug extends DrugRef {
  /** Names as the person entered them for this drug in the base analysis. */
  entered_names: string[];
}

/** A finding the added medicine introduces. Same shape as a main finding, plus the source's own management note. */
export interface TwinFinding extends FindingView {
  /** Text from the interaction record (already checked server-side for dosing language). Null when the record has none. */
  management: string | null;
  /** Always "record" for an added finding. */
  pair_status: string;
  severity_conflict: boolean;
}

/** A pair with no interaction record. NEVER "safe": the screen says so with its own text. */
export interface TwinNoRecordPair {
  drug_a: DrugRef;
  drug_b: DrugRef;
  entered_names_a: string[];
  entered_names_b: string[];
}

export interface SeverityPicture {
  /** null = no known severity at all (this is NOT "safe"). */
  highest_severity: Severity | null;
  counts: Record<Severity, number>;
  total: number;
}

export interface TwinComparison {
  before: SeverityPicture;
  after: SeverityPicture;
  highest_severity_changed: boolean;
  base_findings_count: number;
  new_findings_count: number;
  pairs_checked: number;
}

export interface TwinScenario {
  scenario_id: number;
  base_run_id: number;
  patient_id: number;
  created_at: string;
  /** Always true on a real scenario. The UI labels the whole tab as a simulation either way. */
  simulation: boolean;
  simulation_note: { text_en: string; text_bn: string };
  hypothetical_drug: DrugRef;
  base_drugs: TwinBaseDrug[];
  added_findings: TwinFinding[];
  no_record_pairs: TwinNoRecordPair[];
  comparison: TwinComparison;
  gaps: AnalysisGap[];
  /** Machine codes (interaction_table_only · labs_vitals_not_used · label_passages_not_searched · unresolved_medications_not_checked). */
  limitations: string[];
  guardrail_violations: string[];
  disclaimer_version: string;
}

/** One row of the what-if history of an analysis (no findings, no evidence: open the scenario for those). */
export interface TwinScenarioSummary {
  scenario_id: number;
  hypothetical_drug: DrugRef;
  created_at: string;
  new_findings_count: number;
  highest_severity_after: Severity | null;
  highest_severity_changed: boolean;
}