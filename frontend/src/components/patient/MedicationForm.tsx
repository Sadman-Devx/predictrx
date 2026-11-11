import { useState, type FormEvent } from "react";
import { useI18n, type MessageKey } from "../../i18n";
import { addMedication } from "../../lib/clinical";
import { ApiRequestError } from "../../lib/api";
import type { DrugSuggestion, Medication } from "../../lib/types";
import { DrugAutocomplete } from "./DrugAutocomplete";

interface Props {
  patientId: number;
  onAdded: (m: Medication) => void;
}

export function MedicationForm({ patientId, onAdded }: Props) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<DrugSuggestion | null>(null);
  const [strength, setStrength] = useState("");
  const [frequency, setFrequency] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  function onPick(s: DrugSuggestion | null) {
    setPicked(s);
    if (s?.strength && !strength.trim()) setStrength(s.strength); // prefill, never overwrite
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    const raw = text.trim();
    if (!raw) {
      setError("meds.error.name");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const med = await addMedication(patientId, {
        raw_text: raw,
        brand_name: picked?.kind === "brand" ? picked.brand_name ?? "" : "",
        strength: strength.trim(),
        frequency: frequency.trim(),
        drug_id: picked ? picked.drug_id : null,
      });
      onAdded(med);
      setText("");
      setPicked(null);
      setStrength("");
      setFrequency("");
    } catch (err) {
      setError(err instanceof ApiRequestError && err.status === 0 ? "login.network" : "meds.error.save");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card form-card" onSubmit={onSubmit} noValidate aria-labelledby="add-med-title">
      <h2 id="add-med-title">{t("meds.add")}</h2>

      {error && <p className="alert" role="alert">{t(error)}</p>}

      <div className="field wide">
        <label htmlFor="med-name">{t("meds.name")}</label>
        <DrugAutocomplete id="med-name" text={text} onTextChange={setText} picked={picked} onPick={onPick} />
        <span className="muted small">{t("meds.name.hint")}</span>
      </div>

      <div className="row">
        <label className="field">
          {t("meds.strength")}
          <input type="text" maxLength={40} value={strength} onChange={(e) => setStrength(e.target.value)} />
        </label>
        <label className="field">
          {t("meds.frequency")}
          <input type="text" maxLength={60} value={frequency} onChange={(e) => setFrequency(e.target.value)} />
        </label>
      </div>

      <button type="submit" className="btn" disabled={busy}>
        {busy ? t("meds.saving") : t("meds.save")}
      </button>
    </form>
  );
}