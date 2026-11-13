import { useCallback, useRef, useState } from "react";
import { useI18n, type MessageKey } from "../../i18n";
import { ApiRequestError } from "../../lib/api";
import { addMedication, findDrugId } from "../../lib/clinical";
import { resolveMedications, type DrugSuggestion, type ResolveResult } from "../../lib/drugs";
import type { Medication } from "../../lib/types";
import { DrugAutocomplete } from "../medication/DrugAutocomplete";
import { ResolutionDetail } from "../medication/ResolutionDetail";
import { ResolveBadge } from "../medication/ResolveBadge";

interface Props {
  patientId: number;
  onAdded: (m: Medication) => void;
}

interface Draft {
  rawText: string;
  /** Set only when the user picked a brand from the list. */
  brandName: string;
  strength: string;
  result: ResolveResult | "loading" | "error";
  /** The user accepted a fuzzy match. A fuzzy match is never linked to a drug without this. */
  confirmed: boolean;
}

/**
 * Add one medicine to a patient. The name is resolved by the backend resolver first; the medicine is linked to a drug
 * only for an exact/generic match, or a fuzzy match the user explicitly confirmed. Otherwise it is saved as unresolved.
 */
export function MedicationForm({ patientId, onAdded }: Props) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [frequency, setFrequency] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const seq = useRef(0); // only the latest resolver answer is applied
  const lastQuery = useRef({ name: "", strength: "" });

  const resolve = useCallback(async (name: string, strength: string) => {
    const n = ++seq.current;
    lastQuery.current = { name, strength };
    setDraft((d) => (d ? { ...d, rawText: name, result: "loading", confirmed: false } : d));
    try {
      const { results } = await resolveMedications([{ name, strength: strength || undefined }]);
      if (seq.current !== n) return;
      setDraft((d) => (d ? { ...d, result: results[0] } : d));
    } catch {
      if (seq.current !== n) return;
      setDraft((d) => (d ? { ...d, result: "error" } : d));
    }
  }, []);

  function start(rawText: string, brandName: string, strength: string) {
    setError(null);
    setDraft({ rawText, brandName, strength, result: "loading", confirmed: false });
    void resolve(rawText, strength);
  }

  const onPick = (s: DrugSuggestion) => start(s.name, s.type === "brand" ? s.name : "", s.strength || "");

  function reset() {
    seq.current++; // drop any answer still in flight
    setDraft(null);
    setFrequency("");
    setError(null);
  }

  async function onSave() {
    if (!draft || busy || draft.result === "loading") return;
    setBusy(true);
    setError(null);
    try {
      const r = draft.result;
      const linkable = typeof r === "object" && r.status === "resolved" && (r.match_type !== "fuzzy" || draft.confirmed);
      const drugId = linkable ? await findDrugId(r.generic) : null;
      const med = await addMedication(patientId, {
        raw_text: draft.rawText,
        brand_name: draft.brandName,
        strength: draft.strength.trim(),
        frequency: frequency.trim(),
        drug_id: drugId,
      });
      onAdded(med);
      reset();
    } catch (err) {
      setError(err instanceof ApiRequestError && err.status === 0 ? "login.network" : "meds.error.save");
    } finally {
      setBusy(false);
    }
  }

  const result = draft?.result;
  const needsConfirm =
    typeof result === "object" && result.status === "resolved" && result.match_type === "fuzzy" && !draft?.confirmed;
  const willLink =
    typeof result === "object" && result.status === "resolved" && (result.match_type !== "fuzzy" || draft?.confirmed);

  return (
    <section className="card form-card" aria-labelledby="add-med-title">
      <h2 id="add-med-title">{t("meds.add")}</h2>

      {error && <p className="alert" role="alert">{t(error)}</p>}

      <DrugAutocomplete onPick={onPick} onSubmitText={(txt) => start(txt, "", "")} disabled={busy} />

      {draft && (
        <div className="draft" aria-live="polite">
          <strong>{draft.rawText}{draft.strength ? ` ${draft.strength}` : ""}</strong>

          {result === "loading" && <span className="muted small">{t("med.resolving")}</span>}

          {result === "error" && (
            <span className="med-error small">
              {t("med.error")}{" "}
              <button type="button" className="link-btn" onClick={() => void resolve(draft.rawText, draft.strength)}>
                {t("med.retry")}
              </button>
            </span>
          )}

          {typeof result === "object" && (
            <>
              <ResolveBadge result={result} />
              <ResolutionDetail result={result} onPickCandidate={(c) => void resolve(c, draft.strength)} />
              {needsConfirm && (
                <div>
                  <p className="med-warn small">{t("review.fuzzyNote")}</p>
                  <button type="button" className="btn" onClick={() => setDraft((d) => (d ? { ...d, confirmed: true } : d))}>
                    {t("review.confirmMatch")}
                  </button>
                </div>
              )}
              {typeof result === "object" && result.status === "resolved" && draft.confirmed && (
                <span className="small muted">{t("review.status.confirmed")}</span>
              )}
            </>
          )}

          <div className="form-grid">
            <label className="field">
              {t("meds.strength")}
              <input
                type="text"
                maxLength={40}
                value={draft.strength}
                onChange={(e) => setDraft((d) => (d ? { ...d, strength: e.target.value } : d))}
                // Strength is part of the match, so a changed strength is re-checked when the field loses focus.
                onBlur={() => {
                  if (draft.strength.trim() !== lastQuery.current.strength.trim() && draft.rawText.trim()) {
                    void resolve(draft.rawText, draft.strength.trim());
                  }
                }}
              />
            </label>
            <label className="field">
              {t("meds.frequency")}
              <input type="text" maxLength={60} value={frequency} onChange={(e) => setFrequency(e.target.value)} />
              <span className="muted small">{t("review.freqNote")}</span>
            </label>
          </div>

          {result !== "loading" && !willLink && <p className="muted small">{t("meds.unlinked")}</p>}

          <div className="row">
            <button type="button" className="btn" disabled={busy || result === "loading"} onClick={() => void onSave()}>
              {busy ? t("meds.saving") : t("meds.save")}
            </button>
            <button type="button" className="btn secondary" disabled={busy} onClick={reset}>
              {t("meds.discard")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}