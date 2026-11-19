import { api } from "./api";
import type { Paginated } from "./types";

// Trust Center numbers come from two EXISTING read-only list endpoints; only the `count` field is used.
// If either call fails the page says "unavailable". It never shows a guessed number.

async function countOf(path: string): Promise<number | null> {
  try {
    const res = await api<Paginated<unknown> | unknown[]>(path);
    if (Array.isArray(res)) return res.length;
    return typeof res.count === "number" ? res.count : null;
  } catch {
    return null;
  }
}

export interface KnowledgeCounts {
  drugs: number | null;
  interactions: number | null;
}

export async function loadKnowledgeCounts(): Promise<KnowledgeCounts> {
  const [drugs, interactions] = await Promise.all([
    countOf("/drugs/?page_size=1"),
    countOf("/interactions/?page_size=1"),
  ]);
  return { drugs, interactions };
}
