import { api } from "./api";

// Mirrors backend/apps/drugs/services.py (resolve_brand / search_drugs). Keep in sync with /api/schema/.
export type MatchType = "exact" | "generic" | "fuzzy";
export type UnresolvedReason = "no_match" | "ambiguous" | "low_confidence" | "empty_input" | "input_too_long";

export interface ResolvedMedication {
  status: "resolved";
  input: string;
  generic: string;
  confidence: number; // 0..1 — ALWAYS shown together with its basis (match_type + source + verified)
  verified: boolean; // true only after a pharmacist/mentor reviewed the mapping row
  source: string;
  match_type: MatchType;
  matched_name: string;
  strength: string;
  strength_matched: boolean | null; // null = no strength was typed or the row has none
  aliases: string[];
}

export interface UnresolvedMedication {
  status: "unresolved";
  input: string;
  reason: UnresolvedReason;
  candidates?: string[]; // suggestions to pick from — never applied automatically
}

export type ResolveResult = ResolvedMedication | UnresolvedMedication;

export interface DrugSuggestion {
  type: "brand" | "generic";
  name: string;
  generic: string;
  strength: string;
  dosage_form: string;
  verified: boolean;
  source: string;
}

export function searchDrugs(q: string, limit = 8): Promise<{ results: DrugSuggestion[] }> {
  return api(`/drugs/search/?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export function resolveMedications(items: { name: string; strength?: string }[]): Promise<{ results: ResolveResult[] }> {
  return api("/medications/resolve/", { method: "POST", body: JSON.stringify({ items }) });
}
