import type { ResolveResult } from "./lib/drugs";

/** A row in the Review & Confirm list. `result` is always the backend resolver's answer; nothing is guessed in the UI. */
export type RowResult = ResolveResult | "loading" | "error";

export interface DraftRow {
  id: number;
  /** Exactly what was written / typed (brand as entered). */
  rawText: string;
  strength: string;
  /** Informational only: never sent to the interaction check. */
  frequency: string;
  result: RowResult;
  /** Human-in-the-loop flag: the user accepted a fuzzy match. Reset whenever the row is re-resolved. */
  confirmed: boolean;
}

export type RowState = "loading" | "error" | "unresolved" | "needs_confirm" | "confirmed" | "resolved";

export function rowState(row: DraftRow): RowState {
  const r = row.result;
  if (r === "loading") return "loading";
  if (r === "error") return "error";
  if (r.status === "unresolved") return "unresolved";
  if (row.confirmed) return "confirmed";
  if (r.match_type === "fuzzy") return "needs_confirm"; // a fuzzy match is never accepted silently
  return "resolved";
}

/** Rows that keep "Run analysis" disabled. */
export function isBlocking(row: DraftRow): boolean {
  const s = rowState(row);
  return s === "loading" || s === "error" || s === "unresolved" || s === "needs_confirm";
}

/** One key per distinct list: a double-click reuses it, so the backend creates a single run (idempotency_key). */
export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

const SAMPLE_SOURCE = "sample data (layout preview)";

/**
 * STATIC SAMPLE (Day 5): lets the screen be reviewed before the scan flow exists (Day 8).
 * It is labelled as a sample on screen and is not a real prescription (rule.md §3, §7).
 * It covers every state: resolved, fuzzy (needs confirm), ambiguous (unresolved) and a generic name.
 */
export const SAMPLE_ROWS: DraftRow[] = [
  {
    id: 1,
    rawText: "Napa",
    strength: "500 mg",
    frequency: "1+0+1",
    confirmed: false,
    result: {
      status: "resolved",
      input: "Napa",
      generic: "paracetamol",
      confidence: 0.98,
      verified: false,
      source: SAMPLE_SOURCE,
      match_type: "exact",
      matched_name: "Napa",
      strength: "500 mg",
      strength_matched: true,
      aliases: ["acetaminophen"],
    },
  },
  {
    id: 2,
    rawText: "Napaa",
    strength: "500 mg",
    frequency: "1+1+1",
    confirmed: false,
    result: {
      status: "resolved",
      input: "Napaa",
      generic: "paracetamol",
      confidence: 0.82,
      verified: false,
      source: SAMPLE_SOURCE,
      match_type: "fuzzy",
      matched_name: "Napa",
      strength: "500 mg",
      strength_matched: true,
      aliases: [],
    },
  },
  {
    id: 3,
    rawText: "Met",
    strength: "500 mg",
    frequency: "0+0+1",
    confirmed: false,
    result: {
      status: "unresolved",
      input: "Met",
      reason: "ambiguous",
      candidates: ["Metformin", "Metronidazole"],
    },
  },
  {
    id: 4,
    rawText: "Omeprazole",
    strength: "20 mg",
    frequency: "1+0+0",
    confirmed: false,
    result: {
      status: "resolved",
      input: "Omeprazole",
      generic: "omeprazole",
      confidence: 1,
      verified: false,
      source: SAMPLE_SOURCE,
      match_type: "generic",
      matched_name: "omeprazole",
      strength: "20 mg",
      strength_matched: true,
      aliases: [],
    },
  },
];
