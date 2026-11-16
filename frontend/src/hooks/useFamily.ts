import { useCallback, useEffect, useState } from "react";
import { ApiRequestError } from "../lib/api";
import { getFamilySummary, listFamilyPatients } from "../lib/family";
import type { FamilyPatient, FamilySummary } from "../lib/types";

/**
 *  loading — request in flight
 *  ready   — data is here
 *  gone    — 403 / 404: the consent was withdrawn, the link was removed, or the patient is not shared with this user
 *  error   — network / server problem; "Retry" asks again
 */
export type FamilyLoadState = "loading" | "ready" | "gone" | "error";

/** The patients shared with the signed-in family user. */
export function useFamilyList() {
  const [patients, setPatients] = useState<FamilyPatient[]>([]);
  const [state, setState] = useState<FamilyLoadState>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    setState("loading");
    listFamilyPatients(controller.signal)
      .then((list) => {
        if (cancelled) return;
        setPatients(list);
        setState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setState("error");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { patients, state, retry };
}

/** The read-only summary of one shared patient. */
export function useFamilySummary(patientId: number) {
  const [summary, setSummary] = useState<FamilySummary | null>(null);
  const [state, setState] = useState<FamilyLoadState>("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    setState("loading");
    getFamilySummary(patientId, controller.signal)
      .then((next) => {
        if (cancelled) return;
        setSummary(next);
        setState(next ? "ready" : "error");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setSummary(null);
        const code = err instanceof ApiRequestError ? err.status : 0;
        setState(code === 403 || code === 404 ? "gone" : "error");
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [patientId, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { summary, state, retry };
}