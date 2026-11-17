import { ApiRequestError } from "./api";

/** Flattens DRF error details ({"password": ["..."], "email": ["..."]}) into a list of readable reasons. */
export function collectReasons(details: unknown): string[] {
  if (typeof details === "string") return [details];
  if (Array.isArray(details)) return details.flatMap(collectReasons);
  if (details && typeof details === "object") return Object.values(details).flatMap(collectReasons);
  return [];
}

/** The backend's own reasons for a 400 (weak password, wrong current password, ...), or [] for anything else. */
export function reasonsOf(err: unknown): string[] {
  if (err instanceof ApiRequestError && err.status === 400) {
    return [...new Set(collectReasons(err.body?.error?.details))];
  }
  return [];
}
