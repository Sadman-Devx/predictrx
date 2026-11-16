import { useState, type FormEvent } from "react";
import "../../styles/consent.css";
import { useI18n, type MessageKey } from "../../i18n";
import { ApiRequestError } from "../../lib/api";
import { activeConsent, analysisConsent, CONSENT_SCOPES, consentsOf, recordConsent, revokeConsent } from "../../lib/consent";
import { formatWhen } from "../../lib/format";
import type { ConsentScope, Patient } from "../../lib/types";
import { StatusPill, type Tone } from "../ui/StatusPill";

interface Props {
  patient: Patient;
  /** Called after a consent was recorded or withdrawn: the screen loads the patient again. */
  onChanged: () => Promise<void> | void;
}

const SCOPE_TEXT: Record<ConsentScope, { label: MessageKey; hint: MessageKey }> = {
  analysis: { label: "consent.scope.analysis", hint: "consent.scope.analysis.hint" },
  family_view: { label: "consent.scope.family_view", hint: "consent.scope.family_view.hint" },
  retain_images: { label: "consent.scope.retain_images", hint: "consent.scope.retain_images.hint" },
};

/** Stored as plain English role words (the field is "who gave consent": a role, never a full name). */
const GRANTED_BY: { value: string; key: MessageKey }[] = [
  { value: "Patient", key: "consent.by.patient" },
  { value: "Guardian", key: "consent.by.guardian" },
  { value: "Family caregiver", key: "consent.by.caregiver" },
];

function errorKey(err: unknown, fallback: MessageKey): MessageKey {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) return "login.network";
    if (err.status === 403) return "consent.error.forbidden";
    if (err.status === 404 || err.status === 405) return "consent.error.unavailable";
  }
  return fallback;
}

/**
 * Consent panel (Day 9). Shows, for one patient, which consents are active (analysis, family view, longer image storage),
 * lets the owner record one, and lets the owner withdraw one.
 *
 * Nothing is guessed: if the server does not send the consent list, the panel says it cannot tell and does not show "active".
 * Withdrawing asks once more. Both actions are written to the audit log by the server.
 */
export function ConsentPanel({ patient, onChanged }: Props) {
  const { t, lang } = useI18n();

  const list = consentsOf(patient);
  const overall = analysisConsent(patient);

  const [formScope, setFormScope] = useState<ConsentScope | null>(null);
  const [grantedBy, setGrantedBy] = useState(GRANTED_BY[0].value);
  const [attest, setAttest] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState<MessageKey | null>(null);

  function openForm(scope: ConsentScope) {
    setFormScope(scope);
    setGrantedBy(GRANTED_BY[0].value);
    setAttest(false);
    setConfirmId(null);
    setError(null);
    setNotice(null);
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (busy || formScope === null || !attest) return;
    setBusy(true);
    setError(null);
    try {
      await recordConsent(patient.id, formScope, grantedBy);
      setFormScope(null);
      setNotice("consent.saved");
      await onChanged();
    } catch (err) {
      setError(errorKey(err, "consent.error.save"));
    } finally {
      setBusy(false);
    }
  }

  async function onRevoke(consentId: number) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await revokeConsent(patient.id, consentId);
      setConfirmId(null);
      setNotice("consent.revoked");
      await onChanged();
    } catch (err) {
      setError(errorKey(err, "consent.error.revoke"));
    } finally {
      setBusy(false);
    }
  }

  // ---- banner: the state of the consent that matters most (analysis) ----
  const banner: { tone: Tone; title: MessageKey; text?: MessageKey } =
    overall === "active"
      ? { tone: "ok", title: "consent.banner.active" }
      : overall === "missing"
        ? { tone: "warn", title: "consent.banner.missing.title", text: "consent.banner.missing.text" }
        : { tone: "neutral", title: "consent.banner.unknown.title", text: "consent.banner.unknown.text" };

  return (
    <section className="card consent-panel" aria-labelledby="consent-title">
      <h2 id="consent-title">{t("consent.title")}</h2>
      <p className="muted">{t("consent.hint")}</p>

      <div className={`consent-banner tone-${banner.tone}`} role="note">
        <StatusPill tone={banner.tone}>{t(banner.title)}</StatusPill>
        {banner.text && <p>{t(banner.text)}</p>}
      </div>

      <div role="status" aria-live="polite">
        {notice && <p className="consent-notice">{t(notice)}</p>}
      </div>
      {error && <p className="alert" role="alert">{t(error)}</p>}

      <ul className="consent-list">
        {CONSENT_SCOPES.map((scope) => {
          const active = list ? activeConsent(list, scope) : null;
          const text = SCOPE_TEXT[scope];
          const asking = confirmId !== null && active !== null && active.id === confirmId;
          const tone: Tone = list === null ? "neutral" : active ? "ok" : "warn";
          const statusKey: MessageKey = list === null ? "consent.status.unknown" : active ? "consent.status.active" : "consent.status.none";
          const when = active ? formatWhen(active.granted_at, lang) : "";

          return (
            <li key={scope} className="consent-row">
              <div className="consent-main">
                <strong>{t(text.label)}</strong>
                <span className="muted small">{t(text.hint)}</span>
                {active && (
                  <span className="muted small">
                    {t("consent.givenBy", { who: active.granted_by || "—", when: when || "—" })}
                  </span>
                )}
              </div>

              <div className="consent-side">
                <StatusPill tone={tone}>{t(statusKey)}</StatusPill>

                {active && !asking && (
                  <button type="button" className="btn secondary" disabled={busy} onClick={() => { setConfirmId(active.id); setNotice(null); setError(null); }}>
                    {t("consent.revoke")}
                  </button>
                )}

                {!active && formScope !== scope && (
                  <button type="button" className="btn secondary" disabled={busy} onClick={() => openForm(scope)}>
                    {t("consent.record")}
                  </button>
                )}
              </div>

              {asking && active && (
                <div className="consent-confirm" role="group" aria-label={t("consent.revoke.ask")}>
                  <p>{t("consent.revoke.ask")}</p>
                  <div className="row">
                    <button type="button" className="btn" disabled={busy} onClick={() => void onRevoke(active.id)}>
                      {busy ? t("consent.saving") : t("consent.revoke.yes")}
                    </button>
                    <button type="button" className="btn secondary" disabled={busy} onClick={() => setConfirmId(null)}>
                      {t("consent.revoke.no")}
                    </button>
                  </div>
                </div>
              )}

              {formScope === scope && (
                <form className="consent-form" onSubmit={onSave} noValidate aria-label={t("consent.form.title", { scope: t(text.label) })}>
                  <h3>{t("consent.form.title", { scope: t(text.label) })}</h3>

                  <label className="field">
                    {t("consent.form.by")}
                    <select value={grantedBy} onChange={(e) => setGrantedBy(e.target.value)} disabled={busy}>
                      {GRANTED_BY.map((g) => (
                        <option key={g.value} value={g.value}>{t(g.key)}</option>
                      ))}
                    </select>
                  </label>

                  <label className="confirm-check">
                    <input type="checkbox" checked={attest} onChange={(e) => setAttest(e.target.checked)} disabled={busy} />
                    <span>{t("consent.form.attest")}</span>
                  </label>

                  <div className="row">
                    <button type="submit" className="btn" disabled={busy || !attest}>
                      {busy ? t("consent.saving") : t("consent.form.save")}
                    </button>
                    <button type="button" className="btn secondary" disabled={busy} onClick={() => setFormScope(null)}>
                      {t("patients.cancel")}
                    </button>
                  </div>
                </form>
              )}
            </li>
          );
        })}
      </ul>

      {list === null && <p className="muted small">{t("consent.unknown.note")}</p>}
    </section>
  );
}