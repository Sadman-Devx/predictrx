import { api } from "./api";
import type { ConsentRecord, ConsentScope, Patient } from "./types";

/** Display order. Matches the backend `Consent.SCOPES`. */
export const CONSENT_SCOPES: readonly ConsentScope[] = ["analysis", "family_view", "retain_images"];

/** POST /api/patients/{id}/consents/ — records one consent scope (owner only; the server writes the audit entry). */
export const recordConsent = (patientId: number, scope: ConsentScope, grantedBy: string) =>
  api<unknown>(`/patients/${patientId}/consents/`, {
    method: "POST",
    body: JSON.stringify({ scope, granted_by: grantedBy, granted_at: new Date().toISOString() }),
  });

/** POST /api/patients/{id}/consents/{cid}/revoke/ */
export const revokeConsent = (patientId: number, consentId: number) =>
  api<unknown>(`/patients/${patientId}/consents/${consentId}/revoke/`, {
    method: "POST",
    body: JSON.stringify({}),
  });

/** The consent records the server sent with the patient, or null when it did not send any (nothing is guessed). */
export function consentsOf(patient: Patient): ConsentRecord[] | null {
  if (!Array.isArray(patient.consents)) return null;
  return patient.consents.filter((c) => !!c && typeof c.id === "number" && typeof c.scope === "string");
}

/** The newest consent of this scope that has not been withdrawn, or null. */
export function activeConsent(consents: ConsentRecord[], scope: ConsentScope): ConsentRecord | null {
  const live = consents.filter((c) => c.scope === scope && !c.revoked_at);
  if (live.length === 0) return null;
  return live.reduce((newest, c) => (Date.parse(c.granted_at) > Date.parse(newest.granted_at) ? c : newest));
}

/**
 * Is there an active consent for analysis (needed before a prescription image is read)?
 *  - per-type records sent  → exact answer
 *  - only an overall flag   → "missing" if the flag is false; a true flag does not say WHICH consent is active, so "unknown"
 *  - nothing sent           → "unknown"
 */
export function analysisConsent(patient: Patient): "active" | "missing" | "unknown" {
  const list = consentsOf(patient);
  if (list) return activeConsent(list, "analysis") ? "active" : "missing";
  if (patient.consent_active === false) return "missing";
  return "unknown";
}