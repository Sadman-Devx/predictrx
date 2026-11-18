import { api } from "./api";
import type {
  AgentTraceStep,
  AnalysisListItem,
  AnalysisRunStatus,
  AnalysisStartRequest,
  AnalysisStartResponse,
  Paginated,
  PipelineAgent,
  RunStatus,
  TimelineStage,
  TimelineStageKey,
  TimelineStatus,
} from "./types";

/** Pipeline order (backend-design.md §6.1): Resolver → Clinical Notes → Drug Interaction → Advisory → Verifier. */
export const PIPELINE_AGENTS: readonly PipelineAgent[] = [
  "resolver",
  "clinical_notes",
  "drug_interaction",
  "advisory",
  "verifier",
];

/** POST /api/analysis/ — returns at once with a run id; the work happens in a Celery worker. */
export const startAnalysis = (body: AnalysisStartRequest) =>
  api<AnalysisStartResponse>("/analysis/", { method: "POST", body: JSON.stringify(body) });

/** GET /api/analysis/{id}/ — the polling target. Once `status` is "completed" the same body carries the findings. */
export const getAnalysis = (runId: number, signal?: AbortSignal) =>
  api<AnalysisRunStatus>(`/analysis/${runId}/`, { signal });

function toStep(raw: unknown): AgentTraceStep | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.agent_name !== "string") return null;
  const order = Number(r.step_order);
  const latency = Number(r.latency_ms ?? 0);
  if (!Number.isFinite(order)) return null;

  const step: AgentTraceStep = {
    agent_name: r.agent_name,
    step_order: order,
    latency_ms: Number.isFinite(latency) && latency >= 0 ? latency : 0,
  };
  // Day 7: the Agent trace tab shows what each step read, wrote and called. Anything that is not the expected type is dropped.
  if (typeof r.input_summary === "string") step.input_summary = r.input_summary;
  if (typeof r.output_summary === "string") step.output_summary = r.output_summary;
  if (Array.isArray(r.tool_calls)) step.tool_calls = r.tool_calls;
  return step;
}

/**
 * Accepts a plain array, a paginated `{ results }`, or `{ trace }` / `{ traces }`, so the screen does not break
 * if the trace endpoint's envelope changes. Anything that does not look like a trace row is dropped.
 */
export function parseTrace(body: unknown): AgentTraceStep[] {
  let list: unknown = body;
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const o = body as { results?: unknown; trace?: unknown; traces?: unknown };
    list = o.results ?? o.trace ?? o.traces;
  }
  if (!Array.isArray(list)) return [];
  return list
    .map(toStep)
    .filter((s): s is AgentTraceStep => s !== null)
    .sort((a, b) => a.step_order - b.step_order);
}

/** GET /api/analysis/{id}/trace/ — which agents have run and how long each took. 404 means the endpoint is not deployed yet. */
export async function getAnalysisTrace(runId: number, signal?: AbortSignal): Promise<AgentTraceStep[]> {
  return parseTrace(await api<unknown>(`/analysis/${runId}/trace/`, { signal }));
}

const TIMELINE_KEYS: ReadonlySet<string> = new Set(["photo_upload", "ocr", "resolve", "interaction", "guardrail", "report"]);
const TIMELINE_STATUSES: ReadonlySet<string> = new Set(["done", "running", "failed", "pending", "skipped"]);

/**
 * Reads the `timeline` of the trace endpoint. A stage with an unknown key or status is dropped, and `meta` keeps only
 * finite numbers, so a server change cannot crash the screen. An older server without `timeline` gives an empty list
 * (the run page then falls back to the five-step stepper).
 */
export function parseTimeline(body: unknown): TimelineStage[] {
  if (!body || typeof body !== "object") return [];
  const raw = (body as { timeline?: unknown }).timeline;
  if (!Array.isArray(raw)) return [];

  const stages: TimelineStage[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    if (typeof r.key !== "string" || !TIMELINE_KEYS.has(r.key)) continue;
    if (typeof r.status !== "string" || !TIMELINE_STATUSES.has(r.status)) continue;

    const meta: Record<string, number> = {};
    if (r.meta && typeof r.meta === "object") {
      for (const [k, v] of Object.entries(r.meta as Record<string, unknown>)) {
        if (typeof v === "number" && Number.isFinite(v)) meta[k] = v;
      }
    }
    const ms = typeof r.duration_ms === "number" && Number.isFinite(r.duration_ms) && r.duration_ms >= 0 ? r.duration_ms : null;
    stages.push({ key: r.key as TimelineStageKey, status: r.status as TimelineStatus, duration_ms: ms, meta });
  }
  return stages;
}

export interface TraceBundle {
  steps: AgentTraceStep[];
  timeline: TimelineStage[];
}

/** One request, both views of the trace: the agent rows (Agent trace tab) and the timeline stages. */
export async function getTraceBundle(runId: number, signal?: AbortSignal): Promise<TraceBundle> {
  const body = await api<unknown>(`/analysis/${runId}/trace/`, { signal });
  return { steps: parseTrace(body), timeline: parseTimeline(body) };
}

export const isTerminal = (status: RunStatus) => status === "completed" || status === "failed";

// ---------------------------------------------------------------------------------------------------------------
// Stepper state
// ---------------------------------------------------------------------------------------------------------------
export type StepState = "waiting" | "running" | "done" | "stopped" | "unrecorded";

export interface StepView {
  agent: PipelineAgent;
  state: StepState;
  latencyMs: number | null;
}

/**
 * What the stepper may honestly show.
 *
 * A step is "done" ONLY when the server recorded a trace row for it. Nothing is inferred from elapsed time, so a run
 * whose traces are written only at the end (as today) shows every step as "waiting" while it works and the whole
 * run as "in progress" — never a fake step-by-step animation. If the server does write traces as it goes, the next
 * missing step is shown as "running".
 *
 * Finished runs: a step with no trace row is "no step record" (we do not claim it did or did not run).
 */
export function deriveSteps(status: RunStatus, trace: AgentTraceStep[]): StepView[] {
  const recorded = new Map<string, AgentTraceStep>();
  for (const step of trace) if (!recorded.has(step.agent_name)) recorded.set(step.agent_name, step);
  const anyRecorded = PIPELINE_AGENTS.some((a) => recorded.has(a));
  let frontier = false; // the first step without a record, once some steps have one

  return PIPELINE_AGENTS.map((agent): StepView => {
    const hit = recorded.get(agent);
    if (hit) return { agent, state: "done", latencyMs: hit.latency_ms };
    if (status === "completed") return { agent, state: "unrecorded", latencyMs: null };
    if (status === "queued") return { agent, state: "waiting", latencyMs: null };
    if (!anyRecorded) return { agent, state: status === "failed" ? "unrecorded" : "waiting", latencyMs: null };
    if (!frontier) {
      frontier = true;
      return { agent, state: status === "running" ? "running" : "stopped", latencyMs: null };
    }
    return { agent, state: status === "failed" ? "unrecorded" : "waiting", latencyMs: null };
  });
}

/** GET /api/analysis/runs/ — the signed-in clinician's own runs, newest first. */
export const listAnalyses = (page = 1, status?: RunStatus) =>
  api<Paginated<AnalysisListItem>>(`/analysis/runs/?page=${page}${status ? `&status=${status}` : ""}`);

/** Completed runs for the selected patient, for an explicitly linked clinician follow-up. */
export const listPatientAnalyses = (patientId: number) =>
  api<Paginated<AnalysisListItem>>(`/analysis/runs/?page_size=100&patient=${patientId}&status=completed`);
