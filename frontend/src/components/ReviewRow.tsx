import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import { useI18n, type MessageKey } from "../../i18n";
import { rowState, type DraftRow, type RowState } from "../../lib/review";
import { ResolveBadge } from "./ResolveBadge";

type Tone = "ok" | "warn" | "neutral" | "stop";

const REASON: Record<string, MessageKey> = {
  no_match: "med.reason.no_match",
  ambiguous: "med.reason.ambiguous",
  low_confidence: "med.reason.low_confidence",
  empty_input: "med.reason.invalid",
  input_too_long: "med.reason.invalid",
};

const STATUS: Record<RowState, { tone: Tone; label: MessageKey }> = {
  loading: { tone: "neutral", label: "med.resolving" },
  error: { tone: "stop", label: "med.error" },
  unresolved: { tone: "stop", label: "review.status.unresolved" },
  needs_confirm: { tone: "warn", label: "review.status.needsConfirm" },
  confirmed: { tone: "ok", label: "review.status.confirmed" },
  resolved: { tone: "ok", label: "review.status.resolved" },
};

// Distinct shapes: status is never conveyed by colour alone.
function Glyph({ tone }: { tone: Tone }) {
  const c = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true as const };
  if (tone === "ok") return <svg {...c}><circle cx="6" cy="6" r="5.25" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M3.4 6.2 5.2 8l3.4-3.6" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
  if (tone === "warn") return <svg {...c}><path d="M6 1 11.5 11h-11z" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
  if (tone === "stop") return <svg {...c}><rect x="1.5" y="1.5" width="9" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
  return <svg {...c}><circle cx="6" cy="6" r="5.25" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.5 2" /></svg>;
}

function StatusPill({ state }: { state: RowState }) {
  const { t } = useI18n();
  const { tone, label } = STATUS[state];
  return (
    <span className={`resolve-badge tone-${tone}`}>
      <Glyph tone={tone} />
      {t(label)}
    </span>
  );
}

interface Props {
  row: DraftRow;
  onConfirm: (id: number) => void;
  onRemove: (id: number) => void;
  onSaveEdit: (id: number, v: { rawText: string; strength: string; frequency: string }) => void;
  onPickCandidate: (id: number, name: string) => void;
  onRetry: (id: number) => void;
}

/** One editable medication in the review list: raw text as written, resolved generic, status, edit / remove. */
export function ReviewRow({ row, onConfirm, onRemove, onSaveEdit, onPickCandidate, onRetry }: Props) {
  const { t } = useI18n();
  const uid = useId();
  const state = rowState(row);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(row.rawText);
  const [strength, setStrength] = useState(row.strength);
  const [frequency, setFrequency] = useState(row.frequency);

  const result = typeof row.result === "object" ? row.result : null;
  const label = `${row.rawText}${row.strength ? ` ${row.strength}` : ""}`;

  function startEdit() {
    setName(row.rawText);
    setStrength(row.strength);
    setFrequency(row.frequency);
    setEditing(true);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const n = name.trim();
    if (!n) return;
    setEditing(false);
    onSaveEdit(row.id, { rawText: n, strength: strength.trim(), frequency: frequency.trim() });
  }

  function onKeyDown(e: KeyboardEvent<HTMLFormElement>) {
    if (e.key === "Escape") setEditing(false);
  }

  return (
    <li className={`review-row state-${state}`}>
      {editing ? (
        <form className="review-edit" onSubmit={submit} onKeyDown={onKeyDown} noValidate>
          <label className="review-field" htmlFor={`${uid}-name`}>
            {t("review.field.name")}
            <input id={`${uid}-name`} type="text" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </label>
          <label className="review-field" htmlFor={`${uid}-strength`}>
            {t("review.field.strength")}
            <input id={`${uid}-strength`} type="text" maxLength={40} value={strength} onChange={(e) => setStrength(e.target.value)} />
          </label>
          <label className="review-field" htmlFor={`${uid}-freq`}>
            {t("review.field.frequency")}
            <input id={`${uid}-freq`} type="text" maxLength={60} value={frequency} onChange={(e) => setFrequency(e.target.value)} />
          </label>
          <p className="small muted">{t("review.freqNote")}</p>
          <div className="review-actions">
            <button type="submit" className="btn" disabled={!name.trim()}>{t("review.save")}</button>
            <button type="button" className="btn secondary" onClick={() => setEditing(false)}>{t("review.cancel")}</button>
          </div>
        </form>
      ) : (
        <>
          <div className="review-main">
            <div className="review-head">
              <strong>{label}</strong>
              <StatusPill state={state} />
            </div>

            {row.frequency && (
              <div className="small muted">{t("review.field.frequency")}: {row.frequency}</div>
            )}

            {state === "error" && (
              <div className="med-error small">
                {t("med.error")}{" "}
                <button type="button" className="link-btn" onClick={() => onRetry(row.id)}>{t("med.retry")}</button>
              </div>
            )}

            {result?.status === "resolved" && (
              <div className="small review-detail">
                <div>
                  {t("med.generic")}: <strong>{result.generic}</strong>
                  {result.aliases.length > 0 && <span className="muted"> · {t("med.also")}: {result.aliases.join(", ")}</span>}
                </div>
                {/* Confidence is always shown together with its basis (match type + source). */}
                <ResolveBadge result={result} />
                {result.match_type === "fuzzy" && state === "needs_confirm" && <div className="med-warn">{t("review.fuzzyNote")}</div>}
                {result.strength_matched === false && <div className="med-warn">{t("med.strengthMismatch")}</div>}
              </div>
            )}

            {result?.status === "unresolved" && (
              <div className="small review-detail">
                <p>{t(REASON[result.reason] ?? "med.reason.no_match")}</p>
                {result.candidates && result.candidates.length > 0 && (
                  <div className="med-candidates">
                    {result.candidates.map((c) => (
                      <button key={c} type="button" className="btn secondary" onClick={() => onPickCandidate(row.id, c)}>
                        {t("med.use")} {c}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="review-actions">
            {state === "needs_confirm" && (
              <button type="button" className="btn" onClick={() => onConfirm(row.id)}>{t("review.confirmMatch")}</button>
            )}
            <button type="button" className="btn secondary" disabled={state === "loading"} onClick={startEdit} aria-label={`${t("review.edit")}: ${label}`}>
              {t("review.edit")}
            </button>
            <button type="button" className="btn secondary" onClick={() => onRemove(row.id)} aria-label={`${t("med.remove")}: ${label}`}>
              {t("med.remove")}
            </button>
          </div>
        </>
      )}
    </li>
  );
}
