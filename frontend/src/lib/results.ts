import type { Lang } from "../i18n";
import type { ConfidenceBasis, DoctorSummary, EvidenceItem, RiskFinding, Severity, VerificationStatus } from "./types";

/** Display order: the highest severity first (design.md §1.4). */
export const SEVERITIES: readonly Severity[] = ["major", "moderate", "minor", "unknown"];
export const VERIFICATIONS: readonly VerificationStatus[] = ["verified", "unverified", "conflict"];

const RANK: Record<Severity, number> = { major: 0, moderate: 1, minor: 2, unknown: 3 };

/** The server already sorts major → unknown. This keeps the order right if that ever changes (ties stay in id order). */
export function sortFindings(list: RiskFinding[]): RiskFinding[] {
  return [...list].sort((a, b) => (RANK[a.severity] ?? 3) - (RANK[b.severity] ?? 3) || a.id - b.id);
}

export function severityCounts(list: RiskFinding[]): Record<Severity, number> {
  const out: Record<Severity, number> = { major: 0, moderate: 0, minor: 0, unknown: 0 };
  for (const f of list) if (f.severity in out) out[f.severity] += 1;
  return out;
}

export function verificationCounts(list: RiskFinding[]): Record<VerificationStatus, number> {
  const out: Record<VerificationStatus, number> = { verified: 0, unverified: 0, conflict: 0 };
  for (const f of list) out[normalizeVerification(f.verification_status)] += 1;
  return out;
}

/** An unexpected value from the server is shown as "unverified" (the lowest-trust state), never as "verified". */
export function normalizeVerification(value: string): VerificationStatus {
  return value === "verified" || value === "conflict" ? value : "unverified";
}

export interface PickedSummary {
  text: string;
  /** The language the text is actually written in (may differ from the one the person asked for). */
  lang: Lang;
}

/** The doctor summary in the current language; falls back to the other one (and says which) instead of showing nothing. */
export function pickSummary(summary: DoctorSummary | null | undefined, lang: Lang): PickedSummary | null {
  if (!summary) return null;
  const text: Record<Lang, string> = {
    bn: (summary.doctor_summary_bn ?? "").trim(),
    en: (summary.doctor_summary_en ?? "").trim(),
  };
  const order: Lang[] = lang === "bn" ? ["bn", "en"] : ["en", "bn"];
  for (const l of order) if (text[l]) return { text: text[l], lang: l };
  return null;
}

/** Only http(s) links are ever rendered as links (a source URL comes from stored data: no javascript: or data: URLs). */
export function safeHttpUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

const SOURCE_NAMES: Record<string, string> = {
  ddinter: "DDInter",
  openfda: "openFDA",
  openfda_label: "openFDA label",
};

export function sourceName(source: string, type: string): string {
  const raw = (source ?? "").trim();
  return SOURCE_NAMES[raw.toLowerCase()] ?? (raw || type || "—");
}

/** Chip text: source name + record id, e.g. "DDInter #42" (design.md §4.6 EvidenceChip). */
export function chipText(item: EvidenceItem): string {
  const name = sourceName(item.source, item.type);
  return item.id !== null && item.id !== undefined ? `${name} #${item.id}` : name;
}

/** Name shown for a source in the Evidence panel: the server's `source_name`, else the local fallback. */
export function evidenceSourceName(item: EvidenceItem): string {
  const name = (item.source_name ?? "").trim();
  return name || sourceName(item.source, item.type);
}

/** Link of a source, only when it is a safe http(s) URL. */
export function evidenceLink(item: EvidenceItem): string | null {
  return safeHttpUrl(item.source_url) ?? safeHttpUrl(item.url);
}

/** "Record title · section" line under the source name. */
export function evidenceMeta(item: EvidenceItem): string {
  return [item.label, item.section]
    .map((s) => (s ?? "").trim())
    .filter((s) => s !== "")
    .join(" · ");
}

/** Confidence (0..1) of one evidence entry; a source that came without one uses the finding's own value. */
export function evidenceConfidence(item: EvidenceItem, fallback: number): number {
  return typeof item.confidence === "number" && Number.isFinite(item.confidence) ? item.confidence : fallback;
}

/** Names the person typed that differ from the generic (the brand "as entered"). Duplicates are dropped. */
export function enteredAs(names: string[] | undefined, generic: string): string[] {
  const seen = new Set<string>();
  const wanted = generic.trim().toLowerCase();
  const out: string[] = [];
  for (const n of names ?? []) {
    const key = n.trim().toLowerCase();
    if (!key || key === wanted || seen.has(key)) continue;
    seen.add(key);
    out.push(n.trim());
  }
  return out;
}

export type ConfidenceLevel = "high" | "medium" | "low";

export function confidenceView(value: number): { percent: number; level: ConfidenceLevel } {
  const n = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  const percent = Math.round(n * 100);
  return { percent, level: n >= 0.8 ? "high" : n >= 0.5 ? "medium" : "low" };
}

/** Distinct source names behind a confidence value, for its basis line. */
export function basisSources(basis: ConfidenceBasis): string {
  const names = (basis.sources ?? []).map((s) => sourceName(s, ""));
  return names.length > 0 ? names.join(", ") : "—";
}

/** The name of one tool call in a trace row (`{ tool: "check_interaction", ... }`). */
export function toolName(call: unknown): string {
  if (call && typeof call === "object") {
    const c = call as Record<string, unknown>;
    for (const key of ["tool", "name", "tool_name"]) {
      const v = c[key];
      if (typeof v === "string" && v.trim()) return v.trim();
    }
  }
  return "tool";
}

/** Pretty JSON for the "raw tool calls" box. Long output is cut so a huge trace cannot freeze the page. */
export function formatJson(value: unknown, max = 4000): string {
  let text: string;
  try {
    text = JSON.stringify(value, null, 2) ?? "";
  } catch {
    return "";
  }
  return text.length > max ? `${text.slice(0, max)}\n…` : text;
}