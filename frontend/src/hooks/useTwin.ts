import { useCallback, useEffect, useRef, useState } from "react";
import type { MessageKey } from "../i18n";
import { getTwinScenario, listTwinScenarios, runTwin, summaryOf, twinErrorKey } from "../lib/twin";
import type { TwinScenario, TwinScenarioSummary } from "../lib/types";

/**
 *  idle     — the tab has not been opened yet, nothing was requested
 *  loading  — request in flight
 *  ready    — the list came back (it may be empty)
 *  error    — network / server problem; "Retry" asks again
 */
export type TwinHistoryState = "idle" | "loading" | "ready" | "error";

/** What the person is waiting for right now: a new simulation, or an earlier one being opened. */
export type TwinBusy = "idle" | "running" | "opening";

/** Newest first, one row per scenario (a repeated request returns the same scenario, so it never doubles up). */
function upsert(list: TwinScenarioSummary[], row: TwinScenarioSummary): TwinScenarioSummary[] {
  return [row, ...list.filter((s) => s.scenario_id !== row.scenario_id)];
}

/**
 * State of the What-if tab of one analysis (Day 10).
 *  - The history is requested the first time the tab opens (reading it is audited on the server), not on every render.
 *  - Running a what-if is a normal request: the server answers from the interaction table in the same call (no LLM, no queue).
 *  - A late answer can never overwrite a newer one: every action takes a ticket, and only the latest ticket may write state.
 *  - Nothing here touches the patient's medicine list. A scenario is a stored simulation, not a change.
 */
export function useTwin(runId: number, enabled: boolean) {
  const [history, setHistory] = useState<TwinScenarioSummary[]>([]);
  const [historyState, setHistoryState] = useState<TwinHistoryState>("idle");
  const [scenario, setScenario] = useState<TwinScenario | null>(null);
  const [busy, setBusy] = useState<TwinBusy>("idle");
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);
  const [attempt, setAttempt] = useState(0);
  const ticket = useRef(0);

  // After unmount, no answer may write state.
  useEffect(() => {
    return () => {
      ticket.current += 1;
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let cancelled = false;

    setHistoryState("loading");
    listTwinScenarios(runId, controller.signal)
      .then((rows) => {
        if (cancelled) return;
        // A scenario run while this request was in flight is newer than anything in `rows`: keep it, on top.
        setHistory((current) => current.filter((c) => !rows.some((r) => r.scenario_id === c.scenario_id)).concat(rows));
        setHistoryState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setHistoryState("error");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [runId, enabled, attempt]);

  const run = useCallback(
    async (genericName: string) => {
      const mine = ++ticket.current;
      setBusy("running");
      setErrorKey(null);
      try {
        const next = await runTwin(runId, genericName);
        if (ticket.current !== mine) return;
        setScenario(next);
        setHistory((current) => upsert(current, summaryOf(next)));
      } catch (err) {
        if (ticket.current !== mine) return;
        setErrorKey(twinErrorKey(err));
      } finally {
        if (ticket.current === mine) setBusy("idle");
      }
    },
    [runId],
  );

  const open = useCallback(async (scenarioId: number) => {
    const mine = ++ticket.current;
    setBusy("opening");
    setErrorKey(null);
    try {
      const next = await getTwinScenario(scenarioId);
      if (ticket.current !== mine) return;
      setScenario(next);
    } catch (err) {
      if (ticket.current !== mine) return;
      setErrorKey(twinErrorKey(err));
    } finally {
      if (ticket.current === mine) setBusy("idle");
    }
  }, []);

  const clearError = useCallback(() => setErrorKey(null), []);
  const retryHistory = useCallback(() => setAttempt((a) => a + 1), []);

  return { history, historyState, scenario, busy, errorKey, run, open, clearError, retryHistory };
}