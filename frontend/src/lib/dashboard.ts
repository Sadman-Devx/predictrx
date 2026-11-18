import { api } from "./api";
import type { DashboardSummary } from "./types";

/** GET /api/dashboard/summary/ — owner-scoped counts, recent patients and recent activity. */
export const getDashboardSummary = (signal?: AbortSignal) =>
  api<DashboardSummary>("/dashboard/summary/", { signal });
