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

export interface DrugSuggestion {
  kind: "brand" | "generic";
  label: string;
  brand_name: string | null;
  strength: string | null;
  drug_id: number;
  generic_name: string;
  verified: boolean;
}