import { api } from "./api";
import type { PatientCard } from "./types";

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/**
 * GET /api/analysis/{id}/patient-card/ (backend-design.md §3). The card is written in plain Bangla (`RiskSummary.patient_card_bn`);
 * an English copy is shown only if the server sends one.
 *
 * Returns null when the body has no card text at all: the screen then says so instead of drawing an empty card.
 * Field names are read loosely (`patient_card_bn` / `card_bn` / `text_bn`) so a small rename on the server does not blank the tab.
 */
export function parsePatientCard(body: unknown): PatientCard | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const o = body as Record<string, unknown>;

  const bn = text(o.patient_card_bn) || text(o.card_bn) || text(o.text_bn);
  const en = text(o.patient_card_en) || text(o.card_en) || text(o.text_en);
  if (!bn && !en) return null;

  const run = Number(o.run_id);
  return {
    run_id: Number.isInteger(run) && run > 0 ? run : null,
    text_bn: bn,
    text_en: en,
    disclaimer_version: text(o.disclaimer_version),
    generated_at: text(o.generated_at) || text(o.created_at) || text(o.finished_at) || null,
  };
}

/** Reading the card is audited on the server, so it is only requested when the person opens the Patient card tab. */
export async function getPatientCard(runId: number, signal?: AbortSignal): Promise<PatientCard | null> {
  return parsePatientCard(await api<unknown>(`/analysis/${runId}/patient-card/`, { signal }));
}