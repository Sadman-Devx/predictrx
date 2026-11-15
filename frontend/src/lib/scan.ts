import type { DraftRow } from "../review";
import { api, apiBlob } from "./api";
import { resolveMedications, type ResolveResult } from "./drugs";
import type { ResolutionStatus } from "./types";

// Mirrors backend/apps/clinical (ScanUploadSerializer, ScanDetailSerializer, DraftMedicationSerializer). Keep in sync with /api/schema/.
export type ScanStatus = "queued" | "processing" | "extracted" | "failed";

export interface ScanUploadResponse {
  scan_id: number;
  status: ScanStatus;
  /** true = the same image was just uploaded for this patient, so the existing scan is returned (no second vision call). */
  idempotent_replay: boolean;
  retain_until: string;
}

/** Resolver hint stored with a draft (basis of an automatic match, or suggestions for an unresolved row). */
export interface DraftHint {
  status?: string;
  generic?: string;
  confidence?: number;
  match_type?: string;
  verified?: boolean;
  reason?: string;
  candidates?: string[];
}

/** One DRAFT medicine read from the image. Always `confirmed_by_user: false` until a person confirms it on the Review screen. */
export interface ScanDraft {
  id: number;
  patient: number;
  scan: number | null;
  raw_text: string;
  brand_name: string;
  strength: string;
  frequency: string;
  drug: number | null;
  generic_name: string | null;
  resolution_status: ResolutionStatus;
  confirmed_by_user: boolean;
  source: string;
  resolution: DraftHint | null;
  created_at: string;
}

export interface ScanDetail {
  scan_id: number;
  patient_id: number;
  status: ScanStatus;
  is_final: boolean;
  /** Machine code, "" unless the scan failed. */
  error_code: string;
  retain_until: string;
  image_available: boolean;
  requires_confirmation: boolean;
  /** "clear" | "partial" | "poor" | "unknown" once extracted, otherwise null. */
  legibility: string | null;
  /** null until the scan is "extracted": a partial extraction never looks final. */
  drafts: ScanDraft[] | null;
  created_at: string;
  disclaimer_version: string;
}

/** POST /api/prescriptions/scan/ (multipart). The server decides the file type from the bytes and the patient from the signed-in user. */
export function uploadScan(patientId: number, image: File): Promise<ScanUploadResponse> {
  const form = new FormData();
  form.append("patient_id", String(patientId));
  form.append("image", image);
  return api<ScanUploadResponse>("/prescriptions/scan/", { method: "POST", body: form });
}

/** GET /api/prescriptions/scan/{id}/ — the polling target. The draft list is included once `status` is "extracted". */
export const getScan = (scanId: number, signal?: AbortSignal) =>
  api<ScanDetail>(`/prescriptions/scan/${scanId}/`, { signal });

/** GET /api/prescriptions/scan/{id}/image/ — authenticated and audited; shown from a blob URL (there is no public image URL). */
export const fetchScanImage = (scanId: number, signal?: AbortSignal) =>
  apiBlob(`/prescriptions/scan/${scanId}/image/`, { signal });

/** Body for PATCH /api/medications/{id}/ when the Review screen confirms a scanned row. */
export interface DraftUpdate {
  raw_text: string;
  brand_name: string;
  strength: string;
  frequency: string;
  /** The generic the person accepted. Sent together with the name so the server keeps the link. */
  drug_id: number | null;
  confirmed_by_user: true;
}

/** Edit and confirm one scanned draft IN PLACE (so "Run analysis" does not create a second copy of the medicine). */
export const confirmScanDraft = (medicationId: number, body: DraftUpdate) =>
  api<{ id: number }>(`/medications/${medicationId}/`, { method: "PATCH", body: JSON.stringify(body) });

/** Remove a scanned draft the person deleted on the Review screen (the server refuses if a run was built from it). */
export const deleteScanDraft = (medicationId: number) =>
  api<void>(`/medications/${medicationId}/`, { method: "DELETE" });

/**
 * Turn the scan's drafts into Review rows.
 *
 * Every row is re-checked by the SAME resolver the manual flow uses (one batch call, the backend allows 30), so the Review
 * screen gets the full, honest resolver answer (match type, confidence, source, candidates). Nothing is guessed here:
 * if the resolver cannot be reached the rows come back as "error" and each one offers its own Retry.
 */
export async function draftsToRows(drafts: ScanDraft[]): Promise<DraftRow[]> {
  const base = drafts.map((d, i) => ({
    id: i + 1,
    medicationId: d.id,
    // The resolver gets the medicine NAME as written (the whole line, if there is no separate name).
    rawText: (d.brand_name || d.raw_text).trim(),
    strength: d.strength,
    frequency: d.frequency,
  }));

  let results: ResolveResult[] | null = null;
  try {
    const res = await resolveMedications(base.map((b) => ({ name: b.rawText, strength: b.strength || undefined })));
    if (Array.isArray(res.results) && res.results.length === base.length) results = res.results;
  } catch {
    results = null;
  }

  return base.map(
    (b, i): DraftRow => ({
      ...b,
      confirmed: false,
      result: results ? results[i] : "error",
    }),
  );
}