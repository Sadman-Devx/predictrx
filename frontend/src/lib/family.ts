import { api } from "./api";
import type { FamilyPatient, FamilySummary, Severity } from "./types";

const SEVERITIES: readonly string[] = ["major", "moderate", "minor", "unknown"];

function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function positiveInt(value: unknown): number | null {
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : null;
}

/** Names only. Strength and frequency are left out on purpose: the family view never carries dosing (design.md §1.6). */
function medicineNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    const name = typeof item === "string" ? item.trim() : isObject(item) ? str(item.generic_name) || str(item.name) || str(item.raw_text) : "";
    if (name && !out.includes(name)) out.push(name);
  }
  return out;
}

/** Accepts a plain array or a paginated `{ results }`. Rows without a usable patient id are dropped. */
export function parseFamilyList(body: unknown): FamilyPatient[] {
  const list: unknown = isObject(body) ? body.results : body;
  if (!Array.isArray(list)) return [];
  const out: FamilyPatient[] = [];
  for (const item of list) {
    if (!isObject(item)) continue;
    const id = positiveInt(item.patient_id) ?? positiveInt(item.id);
    if (id === null) continue;
    out.push({ id, patient_code: str(item.patient_code), relationship: str(item.relationship) });
  }
  return out;
}

/**
 * GET /api/family/patients/{id}/summary/ — the read-only latest summary (backend-design.md §3, Family).
 * Field names are read loosely so a small rename on the server does not blank the page; a value that is not the
 * expected type is dropped, and an unknown severity is shown as "no level" (never as a made-up one).
 */
export function parseFamilySummary(body: unknown, fallbackId: number): FamilySummary | null {
  if (!isObject(body)) return null;
  const consent = isObject(body.consent) ? body.consent : {};
  const severity = str(body.highest_severity) || str(body.severity);

  return {
    patient_id: positiveInt(body.patient_id) ?? fallbackId,
    patient_code: str(body.patient_code),
    relationship: str(body.relationship),
    severity: SEVERITIES.includes(severity) ? (severity as Severity) : null,
    text_bn: str(body.summary_bn) || str(body.patient_card_bn),
    text_en: str(body.summary_en) || str(body.patient_card_en),
    medicines: medicineNames(body.medicines),
    updated_at: str(body.updated_at) || str(body.last_updated) || str(body.finished_at) || null,
    consent_granted_by: str(body.consent_granted_by) || str(consent.granted_by),
    disclaimer_version: str(body.disclaimer_version),
  };
}

/** GET /api/family/patients/ — patients linked to the signed-in family user with an active consent. */
export async function listFamilyPatients(signal?: AbortSignal): Promise<FamilyPatient[]> {
  return parseFamilyList(await api<unknown>("/family/patients/", { signal }));
}

/** Every successful read is written to the AuditLog by the server. */
export async function getFamilySummary(patientId: number, signal?: AbortSignal): Promise<FamilySummary | null> {
  return parseFamilySummary(await api<unknown>(`/family/patients/${patientId}/summary/`, { signal }), patientId);
}