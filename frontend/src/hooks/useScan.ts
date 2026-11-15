import { useCallback, useEffect, useState } from "react";
import { ApiRequestError } from "../lib/api";
import { getScan, type ScanDetail } from "../lib/scan";

const POLL_MS = 1500; // normal polling interval while a scan is queued / processing
const MAX_BACKOFF_MS = 8000; // ceiling for the retry delay after failed requests
const MAX_FAILURES = 5; // consecutive failed requests before we stop and offer "Retry"
const MAX_WATCH_MS = 3 * 60 * 1000; // past this we stop polling and say so (the server's own sweeper fails stuck scans)

/**
 * Why the screen cannot show a trustworthy live status right now (same meanings as the analysis run watcher).
 *  not_found    — no such scan for this user (401/403/404: a foreign scan is a 404 on the server)
 *  reconnecting — a request failed; we are retrying (non-final)
 *  connection   — the server could not be reached after several tries (final until Retry)
 *  server       — the server kept answering with errors (final until Retry)
 *  slow         — still not finished after MAX_WATCH_MS; the scan may yet finish (final until Retry)
 */
export type ScanIssue = "not_found" | "reconnecting" | "connection" | "server" | "slow";

export interface ScanWatch {
  scan: ScanDetail | null;
  issue: ScanIssue | null;
  /** Nothing received yet and nothing wrong yet. */
  loading: boolean;
  retry: () => void;
}

/**
 * Polls GET /api/prescriptions/scan/{id}/ until the scan is `extracted` or `failed` (a partial extraction is never shown as final).
 *  - `scanId === null` means "no scan yet": nothing is requested.
 *  - Stops on a final status, on unmount, and after MAX_FAILURES failed requests in a row.
 *  - Backs off after failures instead of hammering a struggling server.
 *  - Pauses while the tab is hidden and checks again the moment it is visible.
 *  - Every request is abortable; answers that arrive after unmount (or for an older scan id) are ignored.
 */
export function useScan(scanId: number | null): ScanWatch {
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [issue, setIssue] = useState<ScanIssue | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setScan(null);
    setIssue(null);
    if (scanId === null) return;
    const id: number = scanId;

    let cancelled = false;
    let stopped = false;
    let inFlight = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;
    let failures = 0;
    const startedAt = Date.now();

    function schedule(ms: number) {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => void tick(), ms);
    }

    function stop(next: ScanIssue | null) {
      stopped = true;
      if (next) setIssue(next);
    }

    async function tick() {
      if (cancelled || stopped || inFlight) return;
      if (document.hidden) return; // onVisible restarts polling
      inFlight = true;
      controller = new AbortController();
      try {
        const detail = await getScan(id, controller.signal);
        if (cancelled) return;
        failures = 0;
        setScan(detail);
        setIssue(null);

        if (detail.status === "extracted" || detail.status === "failed") {
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
  }, [scanId, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);

  // A scan object left over from an earlier id is never shown for the current one.
  const current = scan !== null && scan.scan_id === scanId ? scan : null;

  return {
    scan: current,
    issue: scanId === null ? null : issue,
    loading: scanId !== null && current === null && issue === null,
    retry,
  };
}