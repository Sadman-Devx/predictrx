import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DrugAutocomplete } from "../components/medication/DrugAutocomplete";
import { ReviewRow } from "../components/medication/ReviewRow";
import { useI18n, type MessageKey } from "../i18n";
import { resolveMedications, type DrugSuggestion } from "../lib/drugs";
import { isBlocking, newIdempotencyKey, rowState, SAMPLE_ROWS, type DraftRow } from "../lib/review";

/**
 * Day 5: Review & Confirm (human-in-the-loop).
 * The list starts from STATIC sample data (labelled on screen). Edits are re-resolved by the real backend resolver.
 * "Run analysis" stays disabled until: the list is not empty, nothing is unresolved / unconfirmed / still checking,
 * and the user has ticked the "I checked this list" box. Unresolved rows must be fixed or explicitly removed.
 */
export default function ReviewConfirm() {
  const { t } = useI18n();
  const navigate = useNavigate();

  const [rows, setRows] = useState<DraftRow[]>(SAMPLE_ROWS);
  const [checked, setChecked] = useState(false);
  const [starting, setStarting] = useState(false);

  const nextId = useRef(SAMPLE_ROWS.length + 1);
  const seq = useRef(new Map<number, number>()); // latest request number per row: stale answers are ignored
  const idemKey = useRef<string | null>(null);

  const patch = useCallback((id: number, p: Partial<DraftRow>) => {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...p } : r)));
  }, []);

  /** Any change to the list invalidates the earlier "I checked it" tick and the idempotency key. */
  const touch = useCallback(() => {
    setChecked(false);
    idemKey.current = null;
  }, []);

  const resolve = useCallback(
    async (id: number, name: string, strength: string) => {
      const n = (seq.current.get(id) ?? 0) + 1;
      seq.current.set(id, n);
      patch(id, { result: "loading", confirmed: false });
      try {
        const { results } = await resolveMedications([{ name, strength: strength || undefined }]);
        if (seq.current.get(id) !== n) return;
        patch(id, { result: results[0] });
      } catch {
        if (seq.current.get(id) !== n) return;
        patch(id, { result: "error" });
      }
    },
    [patch],
  );

  const add = useCallback(
    (name: string, strength = "") => {
      const id = nextId.current++;
      setRows((rs) => [...rs, { id, rawText: name, strength, frequency: "", result: "loading", confirmed: false }]);
      touch();
      void resolve(id, name, strength);
    },
    [resolve, touch],
  );

  const onPick = (s: DrugSuggestion) => add(s.name, s.strength || "");

  function onSaveEdit(id: number, v: { rawText: string; strength: string; frequency: string }) {
    patch(id, { rawText: v.rawText, strength: v.strength, frequency: v.frequency });
    touch();
    void resolve(id, v.rawText, v.strength);
  }

  function onPickCandidate(id: number, name: string) {
    const row = rows.find((r) => r.id === id);
    patch(id, { rawText: name });
    touch();
    void resolve(id, name, row?.strength ?? "");
  }

  function onRetry(id: number) {
    const row = rows.find((r) => r.id === id);
    if (row) void resolve(id, row.rawText, row.strength);
  }

  function onRemove(id: number) {
    seq.current.delete(id);
    setRows((rs) => rs.filter((r) => r.id !== id));
    touch();
  }

  const states = rows.map(rowState);
  const pending = states.filter((s) => s === "loading").length;
  const failed = states.filter((s) => s === "error").length;
  const unresolved = states.filter((s) => s === "unresolved").length;
  const needsConfirm = states.filter((s) => s === "needs_confirm").length;
  const blocking = rows.filter(isBlocking).length;

  const reasons: MessageKey[] = [];
  if (rows.length === 0) reasons.push("review.blocked.empty");
  if (pending > 0) reasons.push("review.blocked.pending");
  if (failed > 0) reasons.push("review.blocked.error");
  if (unresolved > 0) reasons.push("review.blocked.unresolved");
  if (needsConfirm > 0) reasons.push("review.blocked.confirm");
  if (rows.length > 0 && blocking === 0 && !checked) reasons.push("review.blocked.check");

  const canRun = reasons.length === 0 && !starting;
  const canTick = rows.length > 0 && blocking === 0;

  function onRun() {
    if (!canRun) return;
    setStarting(true);
    idemKey.current ??= newIdempotencyKey();
    const medications = rows.flatMap((r) =>
      typeof r.result === "object" && r.result.status === "resolved"
        ? [{ raw_text: r.rawText, strength: r.strength, frequency: r.frequency, generic: r.result.generic, user_confirmed: r.confirmed }]
        : [],
    );
    // Day 6 wires this to POST /api/analysis/ and the pipeline stepper. Nothing is fabricated here.
    navigate("/analysis", { state: { idempotencyKey: idemKey.current, medications } });
  }

  const summary =
    blocking > 0 ? t("review.summary.attention").replace("{{n}}", String(blocking)) : rows.length > 0 ? t("review.summary.ready") : "";

  return (
    <section>
      <h1>{t("review.title")}</h1>
      <p className="muted">{t("review.hint")}</p>
      <p className="sample-note" role="note">{t("review.sample")}</p>

      <div className="review-grid">
        <div className="card">
          <h2>{t("review.list.title")}</h2>
          <p className="small muted review-summary" role="status" aria-live="polite">{summary}</p>

          {rows.length === 0 ? (
            <p className="muted">{t("review.empty")}</p>
          ) : (
            <ul className="review-list">
              {rows.map((r) => (
                <ReviewRow
                  key={r.id}
                  row={r}
                  onConfirm={(id) => patch(id, { confirmed: true })}
                  onRemove={onRemove}
                  onSaveEdit={onSaveEdit}
                  onPickCandidate={onPickCandidate}
                  onRetry={onRetry}
                />
              ))}
            </ul>
          )}

          <h2 className="review-add-title">{t("review.addMore")}</h2>
          <DrugAutocomplete onPick={onPick} onSubmitText={(txt) => add(txt)} />
        </div>

        <aside className="review-side" aria-label={t("review.confirm.title")}>
          <div className="card">
            <h2>{t("review.image.title")}</h2>
            <div className="image-slot">
              <p className="muted small">{t("review.image.placeholder")}</p>
            </div>
          </div>

          <div className="card">
            <h2>{t("review.confirm.title")}</h2>

            <label className="confirm-check">
              <input type="checkbox" checked={checked} disabled={!canTick} onChange={(e) => setChecked(e.target.checked)} />
              <span>{t("review.confirm.checkbox")}</span>
            </label>

            {reasons.length > 0 && (
              <div id="run-blocked" className="run-reason small">
                <p>{t("review.blocked.title")}</p>
                <ul>
                  {reasons.map((k) => (
                    <li key={k}>{t(k)}</li>
                  ))}
                </ul>
              </div>
            )}

            <button
              type="button"
              className="btn block"
              disabled={!canRun}
              aria-describedby={reasons.length > 0 ? "run-blocked" : undefined}
              onClick={onRun}
            >
              {starting ? t("review.running") : t("review.run")}
            </button>
          </div>
        </aside>
      </div>
    </section>
  );
}
