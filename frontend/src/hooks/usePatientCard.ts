import { useCallback, useEffect, useState } from "react";
import { ApiRequestError } from "../lib/api";
import { getPatientCard } from "../lib/patientCard";
import type { PatientCard } from "../lib/types";

/**
 *  idle         — the tab has not been opened yet, nothing was requested
 *  loading      — request in flight
 *  ready        — a card with text came back
 *  empty        — the server answered but there is no card text for this run
 *  unavailable  — 404: no card for this run (or the endpoint is not deployed yet)
 *  error        — network / server problem; "Retry" asks again
 */
export type PatientCardState = "idle" | "loading" | "ready" | "empty" | "unavailable" | "error";

/** Loads the patient card once `enabled` turns true (the first time the person opens the tab). Switching tabs does not ask again. */
export function usePatientCard(runId: number, enabled: boolean) {
  const [card, setCard] = useState<PatientCard | null>(null);
  const [state, setState] = useState<PatientCardState>("idle");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let cancelled = false;

    setState("loading");
    getPatientCard(runId, controller.signal)
      .then((next) => {
        if (cancelled) return;
        setCard(next);
        setState(next ? "ready" : "empty");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setCard(null);
        setState(err instanceof ApiRequestError && err.status === 404 ? "unavailable" : "error");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [runId, enabled, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { card, state, retry };
}