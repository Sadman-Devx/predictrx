import { useCallback, useRef, useState } from "react";
import { DrugAutocomplete } from "../components/medication/DrugAutocomplete";
import { ResolveBadge } from "../components/medication/ResolveBadge";
import { useI18n, type MessageKey } from "../i18n";
import { resolveMedications, type DrugSuggestion, type ResolveResult } from "../lib/drugs";

type Row = { id: number; typed: string; strength?: string; result: ResolveResult | "loading" | "error" };

const REASON: Record<string, MessageKey> = {
  no_match: "med.reason.no_match",
  ambiguous: "med.reason.ambiguous",
  low_confidence: "med.reason.low_confidence",
  empty_input: "med.reason.invalid",
  input_too_long: "med.reason.invalid",
};

/** Day 4: manual entry with autocomplete. Every entry goes through the backend resolver; nothing is guessed here. */
export default function MedicationEntry() {
  const { t } = useI18n();
  const [rows, setRows] = useState<Row[]>([]);
  const nextId = useRef(1);

  const resolve = useCallback(async (id: number, name: string, strength?: string) => {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, typed: name, strength, result: "loading" } : r)));
    try {
      const { results } = await resolveMedications([{ name, strength }]);
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, result: results[0] } : r)));
    } catch {
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

  return (
    <section className="card">
      <h1>{t("med.title")}</h1>
      <p className="muted">{t("med.hint")}</p>
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
                  {r.result.status === "resolved" ? (
                    <div className="small">
                      {t("med.generic")}: <strong>{r.result.generic}</strong>
                      {r.result.aliases.length > 0 && <span className="muted"> · {t("med.also")}: {r.result.aliases.join(", ")}</span>}
                      {r.result.strength_matched === false && <div className="med-warn">{t("med.strengthMismatch")}</div>}
                    </div>
                  ) : (
                    <div className="small">
                      <p>{t(REASON[r.result.reason] ?? "med.reason.no_match")}</p>
                      {r.result.candidates && r.result.candidates.length > 0 && (
                        <div className="med-candidates">
                          {r.result.candidates.map((c) => (
                            <button key={c} type="button" className="btn secondary" onClick={() => void resolve(r.id, c)}>
                              {t("med.use")} {c}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
            <button type="button" className="btn secondary" onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}>
              {t("med.remove")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
