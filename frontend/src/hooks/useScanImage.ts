import { useCallback, useEffect, useState } from "react";
import { ApiRequestError } from "../lib/api";
import { fetchScanImage } from "../lib/scan";

/**
 * loading — request in flight
 * ready   — `url` is a blob URL for an <img>
 * gone    — 404: the image was deleted or purged after its retention period (the draft list is still available)
 * error   — anything else (offline, server error, the server sent something that is not an image)
 */
export type ScanImageState =
  | { status: "loading" }
  | { status: "ready"; url: string }
  | { status: "gone" }
  | { status: "error" };

/**
 * Loads the stored prescription image through the authenticated endpoint and exposes it as a blob URL.
 * The blob URL is revoked on unmount / when the scan changes, and answers that arrive late are ignored.
 */
export function useScanImage(scanId: number): { state: ScanImageState; retry: () => void } {
  const [state, setState] = useState<ScanImageState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    const controller = new AbortController();
    setState({ status: "loading" });

    fetchScanImage(scanId, controller.signal)
      .then((blob) => {
        if (cancelled) return;
        // Only show something the server declared as an image.
        if (!blob.type.startsWith("image/")) {
          setState({ status: "error" });
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setState({ status: "ready", url: objectUrl });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState(err instanceof ApiRequestError && err.status === 404 ? { status: "gone" } : { status: "error" });
      });

    return () => {
      cancelled = true;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [scanId, attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  return { state, retry };
}