import { api } from "./api";
import type { FollowUpTask, Paginated, Patient, PatientAnalysisHistory } from "./types";

// Review Queue: a suggested ORDER in which to look at patients, from a few plain rules over data the app already holds.
// There is no score, no AI and no clinical priority. Each patient is listed with the rules that applied, so the order
// can always be checked by a person. A patient with no flag has NOT been shown to be safe.

export const MAX_PATIENTS = 50;
export const STALE_DAYS = 30;
const CONCURRENCY = 5;

/** Order = priority of the rule. The first reason of a patient decides where the patient is listed. */
export const REASON_ORDER = [
  "conflict",
  "major",
  "overdue",
  "unverified",
  "moderate",
  "noAnalysis",
  "stale",
  "openFollowup",
  "noConsent",
] as const;

export type ReasonKind = (typeof REASON_ORDER)[number];

export interface Reason {
  kind: ReasonKind;
  /** Count the reason is about (findings or tasks). */
  n?: number;
  days?: number;
}

export interface QueueRow {
  patient: Patient;
  latestRunId: number | null;
  reasons: Reason[];
}

export interface QueueData {
  patients: Patient[];
  totalPatients: number;
  histories: Map<number, PatientAnalysisHistory>;
  failedPatientIds: number[];
  /** null = the follow-up list could not be loaded (the page says so; overdue flags may be missing). */
  followUps: FollowUpTask[] | null;
}

export interface Queue {
  flagged: QueueRow[];
  clear: QueueRow[];
}

const DAY_MS = 24 * 60 * 60 * 1000;

function localDateString(now: Date): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Pure function: same data in, same order out. Unit-checkable without a server. */
export function buildQueue(
  patients: Patient[],
  histories: Map<number, PatientAnalysisHistory>,
  followUps: FollowUpTask[] | null,
  now: Date,
): Queue {
  const today = localDateString(now);
  const rows: QueueRow[] = patients.map((patient) => {
    const reasons: Reason[] = [];
    const history = histories.get(patient.id);
    const latest = history && history.results.length > 0 ? history.results[history.results.length - 1] : null;

    if (latest) {
      const conflict = latest.verification_counts.conflict;
      const major = latest.severity_counts.major;
      const unverified = latest.verification_counts.unverified;
      const moderate = latest.severity_counts.moderate;
      if (conflict > 0) reasons.push({ kind: "conflict", n: conflict });
      if (major > 0) reasons.push({ kind: "major", n: major });
      if (unverified > 0) reasons.push({ kind: "unverified", n: unverified });
      if (moderate > 0) reasons.push({ kind: "moderate", n: moderate });
      if (latest.occurred_at) {
        const when = new Date(latest.occurred_at).getTime();
        if (!Number.isNaN(when)) {
          const days = Math.floor((now.getTime() - when) / DAY_MS);
          if (days >= STALE_DAYS) reasons.push({ kind: "stale", days });
        }
      }
    } else if (history && (patient.medication_count ?? 0) > 0) {
      reasons.push({ kind: "noAnalysis" });
    }

    if (followUps) {
      const open = followUps.filter((f) => f.patient_id === patient.id && f.status !== "done");
      const overdue = open.filter((f) => f.due_date != null && f.due_date < today).length;
      if (overdue > 0) reasons.push({ kind: "overdue", n: overdue });
      if (open.length - overdue > 0) reasons.push({ kind: "openFollowup", n: open.length - overdue });
    }

    if (patient.consent_active === false) reasons.push({ kind: "noConsent" });

    reasons.sort((a, b) => REASON_ORDER.indexOf(a.kind) - REASON_ORDER.indexOf(b.kind));
    return { patient, latestRunId: latest ? latest.run_id : null, reasons };
  });

  const flagged = rows
    .filter((r) => r.reasons.length > 0)
    .sort((a, b) => {
      const tier = REASON_ORDER.indexOf(a.reasons[0].kind) - REASON_ORDER.indexOf(b.reasons[0].kind);
      if (tier !== 0) return tier;
      if (b.reasons.length !== a.reasons.length) return b.reasons.length - a.reasons.length;
      return a.patient.patient_code.localeCompare(b.patient.patient_code);
    });
  const clear = rows
    .filter((r) => r.reasons.length === 0)
    .sort((a, b) => a.patient.patient_code.localeCompare(b.patient.patient_code));
  return { flagged, clear };
}

/** Runs `work` over `items`, at most `limit` at a time (the history read is audited per patient, so no burst). */
async function pool<T>(items: T[], limit: number, work: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (next < items.length) {
      const item = items[next++];
      await work(item);
    }
  });
  await Promise.all(runners);
}

/** Reads only existing, owner-scoped endpoints: patients, each patient's analysis history, and the follow-up list. */
export async function loadQueueData(signal?: AbortSignal): Promise<QueueData> {
  const page = await api<Paginated<Patient>>(`/patients/?page_size=${MAX_PATIENTS}`, { signal });
  const patients = page.results.slice(0, MAX_PATIENTS);

  const histories = new Map<number, PatientAnalysisHistory>();
  const failedPatientIds: number[] = [];

  const followUpsPromise = api<Paginated<FollowUpTask>>("/follow-ups/?page_size=100", { signal })
    .then((r) => r.results)
    .catch(() => null);

  await pool(patients, CONCURRENCY, async (p) => {
    try {
      histories.set(p.id, await api<PatientAnalysisHistory>(`/patients/${p.id}/analysis-history/`, { signal }));
    } catch {
      failedPatientIds.push(p.id);
    }
  });

  return {
    patients,
    totalPatients: page.count,
    histories,
    failedPatientIds,
    followUps: await followUpsPromise,
  };
}
