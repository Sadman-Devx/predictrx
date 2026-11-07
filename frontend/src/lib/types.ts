// Keep in sync with the backend OpenAPI schema (/api/schema/). TODO: generate from the schema.
export type Severity = "major" | "moderate" | "minor" | "unknown";
export type VerificationStatus = "verified" | "unverified" | "conflict";

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
