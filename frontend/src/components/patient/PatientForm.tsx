import { useState, type FormEvent } from "react";
import { useI18n, type MessageKey } from "../../i18n";
import { ApiRequestError } from "../../lib/api";
import { createPatient } from "../../lib/clinical";
import type { Patient, PatientInput, Sex } from "../../lib/types";

interface Props {
  onCreated: (p: Patient) => void;
  onCancel: () => void;
}

const SEXES: { value: Sex | ""; key: MessageKey }[] = [
  { value: "", key: "patients.sex.none" },
  { value: "male", key: "patients.sex.male" },
  { value: "female", key: "patients.sex.female" },
  { value: "other", key: "patients.sex.other" },
];

export function PatientForm({ onCreated, onCancel }: Props) {
  const { t } = useI18n();
  const [birthYear, setBirthYear] = useState("");
  const [sex, setSex] = useState<Sex | "">("");
  const [weight, setWeight] = useState("");
  const [errors, setErrors] = useState<{ birthYear?: MessageKey; weight?: MessageKey; form?: MessageKey }>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;

    const next: typeof errors = {};
    const year = birthYear.trim() ? Number(birthYear) : null;
    if (year !== null && (!Number.isInteger(year) || year < 1900 || year > new Date().getFullYear())) {
      next.birthYear = "patients.error.birthYear";
    }
    const w = weight.trim() ? Number(weight) : null;
    if (w !== null && (!Number.isFinite(w) || w <= 0 || w > 500)) next.weight = "patients.error.weight";
    setErrors(next);
    if (next.birthYear || next.weight) return;

    const payload: PatientInput = {};
    if (year !== null) payload.birth_year = year;
    if (sex) payload.sex = sex;
    if (w !== null) payload.weight_kg = String(w);

    setBusy(true);
    try {
      onCreated(await createPatient(payload));
    } catch (err) {
      const status = err instanceof ApiRequestError ? err.status : 0;
      setErrors({ form: status === 0 ? "login.network" : "patients.error.save" });
      setBusy(false);
    }
  }

  return (
    <form className="card form-card" onSubmit={onSubmit} noValidate aria-labelledby="new-patient-title">
      <h2 id="new-patient-title">{t("patients.new.title")}</h2>
      <p className="muted">{t("patients.new.hint")}</p>

      {errors.form && <p className="alert" role="alert">{t(errors.form)}</p>}

      <label className="field">
        {t("patients.birthYear")}
        <input
          type="text"
          inputMode="numeric"
          maxLength={4}
          value={birthYear}
          onChange={(e) => setBirthYear(e.target.value.replace(/\D/g, ""))}
          aria-invalid={!!errors.birthYear}
          aria-describedby={errors.birthYear ? "err-birth" : undefined}
        />
        {errors.birthYear && <span id="err-birth" className="field-error">{t(errors.birthYear)}</span>}
      </label>

      <label className="field">
        {t("patients.sex")}
        <select value={sex} onChange={(e) => setSex(e.target.value as Sex | "")}>
          {SEXES.map((s) => (
            <option key={s.value} value={s.value}>{t(s.key)}</option>
          ))}
        </select>
      </label>

      <label className="field">
        {t("patients.weight")}
        <input
          type="text"
          inputMode="decimal"
          value={weight}
          onChange={(e) => setWeight(e.target.value.replace(/[^\d.]/g, ""))}
          aria-invalid={!!errors.weight}
          aria-describedby={errors.weight ? "err-weight" : undefined}
        />
        {errors.weight && <span id="err-weight" className="field-error">{t(errors.weight)}</span>}
      </label>

      <div className="row">
        <button type="submit" className="btn" disabled={busy}>
          {busy ? t("patients.saving") : t("patients.save")}
        </button>
        <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>
          {t("patients.cancel")}
        </button>
      </div>
    </form>
  );
}