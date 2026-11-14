import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DrugAutocomplete } from "../components/medication/DrugAutocomplete";
import { ResolutionDetail } from "../components/medication/ResolutionDetail";
import { ResolveBadge } from "../components/medication/ResolveBadge";
import { PageHeader } from "../components/ui/PageHeader";
import { useI18n } from "../i18n";
import { resolveMedications, type DrugSuggestion, type ResolveResult } from "../lib/drugs";
import type { DraftRow, ReviewNavState } from "../review";

type Row = { id: number; typed: string; strength?: string; result: ResolveResult | "loading" | "error" };

/** Day 4: manual entry with autocomplete. Every entry goes through the backend resolver; nothing is guessed here. */
export default function MedicationEntry() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [rows, setRows] = useState<Row[]>([]);
  const nextId = useRef(1);
  const seq = useRef(new Map<number, number>()); // latest request number per row: a stale answer never overwrites a newer one

  const resolve = useCallback(async (id: number, name: string, strength?: string) => {
    const n = (seq.current.get(id) ?? 0) + 1;
    seq.current.set(id, n);
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, typed: name, strength, result: "loading" } : r)));
    try {
      const { results } = await resolveMedications([{ name, strength }]);
      if (seq.current.get(id) !== n) return;
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, result: results[0] } : r)));
    } catch {
      if (seq.current.get(id) !== n) return;
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, result: "error" } : r)));
    }
  }, []);

  const add = useCallback(
    (name: string, strength?: string) => {
      const id = nextId.current++;
      setRows((rs) => [...rs, { id, typed: name, strength, result: "loading" }]);
      void resolve(id, name, strength);
    },
    [resolve],
  );

  const onPick = (s: DrugSuggestion) => add(s.name, s.strength || undefined);

  const pending = rows.some((r) => r.result === "loading");
  const canContinue = rows.length > 0 && !pending;

  /** Hand the list to Review & Confirm: that screen holds the human-in-the-loop checks (fuzzy matches, unresolved rows). */
  function onContinue() {
    if (!canContinue) return;
    const draft: DraftRow[] = rows.map((r) => ({
      id: r.id,
      rawText: r.typed,
      strength: r.strength ?? "",
      frequency: "",
      result: r.result,
      confirmed: false,
    }));
    const state: ReviewNavState = { rows: draft };
    navigate("/review", { state });
  }

  return (
    <section>
      <PageHeader title={t("med.title")} subtitle={t("med.hint")} />

      <div className="card">
        <DrugAutocomplete onPick={onPick} onSubmitText={(txt) => add(txt)} />

        <h2 className="med-list-title">{t("med.list.title")}</h2>
        {rows.length === 0 && <p className="muted">{t("med.list.empty")}</p>}
        <ul className="med-list" aria-live="polite">
          {rows.map((r) => (
            <li key={r.id} className="med-row">
              <div className="med-main">
                <strong>{r.typed}{r.strength ? ` ${r.strength}` : ""}</strong>

                {r.result === "loading" && <span className="muted small">{t("med.resolving")}</span>}

                {r.result === "error" && (
                  <span className="med-error">
                    {t("med.error")}{" "}
                    <button type="button" className="link-btn" onClick={() => void resolve(r.id, r.typed, r.strength)}>
                      {t("med.retry")}
                    </button>
                  </span>
                )}

                {typeof r.result === "object" && (
                  <>
                    <ResolveBadge result={r.result} />
                    <ResolutionDetail result={r.result} onPickCandidate={(c) => void resolve(r.id, c)} />
                  </>
                )}
              </div>
              <button
                type="button"
                className="btn secondary"
                onClick={() => {
                  seq.current.delete(r.id);
                  setRows((rs) => rs.filter((x) => x.id !== r.id));
                }}
                aria-label={`${t("med.remove")}: ${r.typed}`}
              >
                {t("med.remove")}
              </button>
            </li>
          ))}
        </ul>

        <div className="entry-footer">
          <button type="button" className="btn" disabled={!canContinue} onClick={onContinue} aria-describedby="continue-hint">
            {t("med.continue")}
          </button>
          {!canContinue && <p id="continue-hint" className="muted small">{t("med.continue.blocked")}</p>}
        </div>
      </div>
    </section>
  );
}