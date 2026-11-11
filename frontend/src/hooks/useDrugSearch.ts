import { useEffect, useState } from "react";
import { searchDrugs, type DrugSuggestion } from "../lib/drugs";

export type SearchState = "idle" | "loading" | "ready" | "error";
const MIN_CHARS = 2;
const DEBOUNCE_MS = 200;

/** Debounced autocomplete. A response for an older query can never overwrite a newer one. */
export function useDrugSearch(query: string) {
  const [state, setState] = useState<SearchState>("idle");
  const [results, setResults] = useState<DrugSuggestion[]>([]);

  useEffect(() => {
    const q = query.trim();
    if (q.length < MIN_CHARS) {
      setState("idle");
      setResults([]);
      return;
    }
    let stale = false;
    setState("loading");
    const timer = window.setTimeout(() => {
      searchDrugs(q)
        .then((res) => {
          if (stale) return;
          setResults(res.results);
          setState("ready");
        })
        .catch(() => {
          if (stale) return;
          setResults([]);
          setState("error");
        });
    }, DEBOUNCE_MS);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  return { state, results };
}
