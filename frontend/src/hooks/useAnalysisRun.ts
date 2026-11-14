import { useCallback, useEffect, useState } from "react";
import { getAnalysis, getAnalysisTrace } from "../lib/analysis";
import { ApiRequestError } from "../lib/api";
import type { AgentTraceStep, AnalysisRunStatus } from "../lib/types";

const POLL_MS = 1500; // normal polling interval while a run is queued / running
const MAX_BACKOFF_MS = 8000; // ceiling for the retry delay after failed requests
const MAX_FAILURES = 5; // consecutive failed requests before we stop and offer "Retry"
const MAX_WATCH_MS = 6 * 60 * 1000; // the worker's own limit is ~270 s; past this we stop polling and say so

/**
 * Why the screen cannot show a trustworthy live status right now.
 *  not_found    — no such run for this user (also 401/403: a foreign run is a 404 on the server)
 *  reconnecting — a request failed; we are retrying (non-final)
 *  connection   — the server could not be reached after several tries (final until Retry)
 *  server       — the server kept answering with errors (final until Retry)
 *  slow         — still not finished after MAX_WATCH_MS; the run may yet finish (final until Retry)
 */
export type PollIssue = "not_found" | "reconnecting" | "connection" | "server" | "slow";

export interface AnalysisRunWatch {
  run: AnalysisRunStatus | null;
  /** Trace rows recorded so far (empty until the server has any). */
  trace: AgentTraceStep[];
  /** True once the trace endpoint has answered at least once. */
  traceKnown: boolean;
  issue: PollIssue | null;
  /** Nothing received yet and nothing wrong yet. */
  loading: boolean;
  /** Start polling again after a final issue. */
  retry: () => void;
}

/**
 * Polls GET /api/analysis/{id}/ until the run is completed or failed (rule.md §5: a partial run is never shown as final).
 *  - Stops on a terminal status, on unmount, and after MAX_FAILURES failed requests in a row.
 *  - Backs off after failures (1.5 s → … → 8 s) instead of hammering a struggling server.
 *  - Pauses while the tab is hidden and checks again the moment it is visible.
 *  - Every request is abortable; answers that arrive after unmount are ignored.
 *  - The trace endpoint is optional: a 404 turns trace polling off for this watch, other trace errors are non-fatal.
 */
export function useAnalysisRun(runId: number): AnalysisRunWatch {
  const valid = Number.isInteger(runId) && runId > 0;
  const [run, setRun] = useState<AnalysisRunStatus | null>(null);
  const [trace, setTrace] = useState<AgentTraceStep[]>([]);
  const [traceKnown, setTraceKnown] = useState(false);
  const [issue, setIssue] = useState<PollIssue | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!valid) return;

    let cancelled = false;
    let stopped = false; // terminal status reached, or we gave up
    let inFlight = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    let failures = 0;
    let traceSupported = true;
    const startedAt = Date.now();

    setIssue(null);

    function schedule(ms: number) {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void tick(), ms);
    }

    function stop(next: PollIssue | null) {
      stopped = true;
      if (next) setIssue(next);
    }

    async function tick() {
      if (cancelled || stopped || inFlight) return;
      if (document.hidden) return; // onVisible restarts polling
      inFlight = true;
      controller = new AbortController();
      const { signal } = controller;
      try {
        const status = await getAnalysis(runId, signal);
        if (cancelled) return;
        failures = 0;
        setRun(status);
        setIssue(null);

        if (status.status !== "queued" && traceSupported) {
          try {
            const steps = await getAnalysisTrace(runId, signal);
            if (cancelled) return;
            setTrace(steps);
            setTraceKnown(true);
          } catch (err) {
            if (cancelled) return;
            if (err instanceof ApiRequestError && err.status === 404) traceSupported = false;
            // any other trace error is non-fatal: the status above is what matters
          }
        }

        if (status.status === "completed" || status.status === "failed") {
          stop(null);
          return;
        }
        if (Date.now() - startedAt > MAX_WATCH_MS) {
          stop("slow");
          return;
        }
        schedule(POLL_MS);
      } catch (err) {
        if (cancelled) return;
        const code = err instanceof ApiRequestError ? err.status : 0;
        if (code === 401 || code === 403 || code === 404) {
          stop("not_found"); // a 401 also triggers the app-wide session-expired handler
          return;
        }
        failures += 1;
        if (failures >= MAX_FAILURES) {
          stop(code === 0 ? "connection" : "server");
          return;
        }
        setIssue("reconnecting");
        schedule(Math.min(POLL_MS * 2 ** failures, MAX_BACKOFF_MS));
      } finally {
        inFlight = false;
      }
    }

    function onVisible() {
      if (document.hidden || stopped || inFlight) return;
      window.clearTimeout(timer);
      void tick();
    }

    document.addEventListener("visibilitychange", onVisible);
    void tick();

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [runId, valid, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);

  return {
    run,
    trace,
    traceKnown,
    issue: valid ? issue : "not_found",
    loading: valid && run === null && issue === null,
    retry,
  };
}