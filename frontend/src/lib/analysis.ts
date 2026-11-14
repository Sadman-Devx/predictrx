import { api } from "./api";
import type {
  AgentTraceStep,
  AnalysisRunStatus,
  AnalysisStartRequest,
  AnalysisStartResponse,
  PipelineAgent,
  RunStatus,
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

/** GET /api/analysis/{id}/ — the polling target. */
export const getAnalysis = (runId: number, signal?: AbortSignal) =>
  api<AnalysisRunStatus>(`/analysis/${runId}/`, { signal });

function toStep(raw: unknown): AgentTraceStep | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.agent_name !== "string") return null;
  const order = Number(r.step_order);
  const latency = Number(r.latency_ms ?? 0);
  if (!Number.isFinite(order)) return null;
  return { agent_name: r.agent_name, step_order: order, latency_ms: Number.isFinite(latency) && latency >= 0 ? latency : 0 };
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