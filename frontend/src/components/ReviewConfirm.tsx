import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { DrugAutocomplete } from "./medication/DrugAutocomplete";
import { ReviewRow } from "./ReviewRow";
import { PageHeader } from "./ui/PageHeader";
import { useI18n, type MessageKey, type MessageVars } from "../i18n";
import { startAnalysis } from "../lib/analysis";
import { ApiRequestError } from "../lib/api";
import { addMedication, findDrugId, listPatientOptions } from "../lib/clinical";
import { resolveMedications, type DrugSuggestion, type ResolvedMedication } from "../lib/drugs";
import type { Patient } from "../lib/types";
import { isBlocking, newIdempotencyKey, rowsFromState, rowState, SAMPLE_ROWS, type DraftRow } from "../review";

const MAX_MEDICATIONS = 20; // backend: MAX_MEDICATIONS_PER_RUN
const MIN_DISTINCT_DRUGS = 2; // backend: MIN_DISTINCT_DRUGS

interface StartError {
  key: MessageKey;
  vars?: MessageVars;
}

/** The resolver's answer for a row, only when it is a resolved match. */
function resolvedOf(row: DraftRow): ResolvedMedication | null {
  return typeof row.result === "object" && row.result.status === "resolved" ? row.result : null;
}

function patientIdFrom(value: unknown): number | null {
  const n = typeof value === "string" ? Number(value) : value;
  return typeof n === "number" && Number.isInteger(n) && n > 0 ? n : null;
}

/** A saved medicine can be reused on a retry only while nothing about it (or its patient) has changed. */
function signature(patientId: number, row: DraftRow, generic: string): string {
  return [patientId, row.rawText, row.strength.trim(), row.frequency.trim(), generic.trim().toLowerCase()].join("|");
}

type Stage = "link" | "save" | "start";

function startErrorFor(err: unknown, stage: Stage): StartError {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) return { key: "login.network" };
    if (stage !== "start") return { key: "review.error.save" };
    if (err.status === 429) return { key: "review.error.tooMany" };
    if (err.status === 404) return { key: "review.error.patient" };
    if (err.status === 409) return { key: "review.error.conflict" };
    const code = (err.body?.error?.details as { code?: string } | undefined)?.code;
    if (code === "unresolved_medications" || code === "unconfirmed_medications") return { key: "review.blocked.unresolved" };
    if (code === "not_enough_drugs") return { key: "review.blocked.min" };
    if (err.status >= 500) return { key: "login.server" };
  }
  return { key: stage === "start" ? "review.error.start" : "review.error.save" };
}

/**
 * Day 5: Review & Confirm (human-in-the-loop). Day 6: "Run analysis" now starts a real run.
 *
 * The list comes from manual entry (router state). Opened directly, it falls back to a STATIC sample that is labelled on screen,
 * and a sample can never be analysed (it is not a real prescription and must not be saved to a patient's record).
 * Edits are re-resolved by the real backend resolver.
 * "Run analysis" stays disabled until: a patient is chosen, the list is not empty, nothing is unresolved / unconfirmed / still checking,
 * at least two different drugs are present, and the user has ticked the "I checked this list" box.
 *
 * On click: (1) every resolved generic is linked to a Drug id (nothing is saved if one cannot be linked),
 * (2) the medicines are saved to the patient's record, (3) POST /api/analysis/ with one idempotency key per list,
 * (4) the progress page /analysis/:runId opens. Medicines already saved for an unchanged list are reused on a retry,
 * so a failed attempt followed by a retry does not create duplicates.
 */
export default function ReviewConfirm() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const [entered] = useState(() => rowsFromState(location.state));
  const isSample = entered === null;

  const [rows, setRows] = useState<DraftRow[]>(() => entered ?? SAMPLE_ROWS);
  const [checked, setChecked] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<StartError | null>(null);

  // Patient picker. A patient can be pre-selected via router state `{ patientId }` or `?patient=ID`; it is never guessed.
  const [patients, setPatients] = useState<Patient[] | null>(null);
  const [patientsFailed, setPatientsFailed] = useState(false);
  const [patientId, setPatientId] = useState<number | null>(
    () =>
      patientIdFrom((location.state as { patientId?: unknown } | null)?.patientId) ??
      patientIdFrom(searchParams.get("patient")),
  );

  const nextId = useRef(rows.reduce((max, r) => Math.max(max, r.id), 0) + 1);
  const seq = useRef(new Map<number, number>()); // latest request number per row: stale answers are ignored
  const idemKey = useRef<string | null>(null);
  const saved = useRef(new Map<number, { sig: string; medicationId: number }>()); // row id -> medicine already saved for it
  const patientsSeq = useRef(0);

  const loadPatients = useCallback(async () => {
    const n = ++patientsSeq.current;
    setPatientsFailed(false);
    try {
      const list = await listPatientOptions();
      if (patientsSeq.current !== n) return;
      setPatients(list);
      // A pre-selected id that is not one of this doctor's patients is dropped, not trusted.
      setPatientId((cur) => (cur !== null && list.some((p) => p.id === cur) ? cur : null));
    } catch {
      if (patientsSeq.current !== n) return;
      setPatientsFailed(true);
    }
  }, []);

  useEffect(() => {
    void loadPatients();
    return () => {
      patientsSeq.current++; // ignore an answer that arrives after leaving the screen
    };
  }, [loadPatients]);

  const patch = useCallback((id: number, p: Partial<DraftRow>) => {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...p } : r)));
  }, []);

  /** Any change to the list or the patient invalidates the earlier "I checked it" tick, the error and the idempotency key. */
  const touch = useCallback(() => {
    setChecked(false);
    setStartError(null);
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
  const distinctGenerics = new Set(rows.flatMap((r) => resolvedOf(r)?.generic.trim().toLowerCase() ?? [])).size;

  const reasons: MessageKey[] = [];
  if (isSample) reasons.push("review.blocked.sample");
  if (rows.length === 0) reasons.push("review.blocked.empty");
  if (rows.length > MAX_MEDICATIONS) reasons.push("review.blocked.max");
  if (pending > 0) reasons.push("review.blocked.pending");
  if (failed > 0) reasons.push("review.blocked.error");
  if (unresolved > 0) reasons.push("review.blocked.unresolved");
  if (needsConfirm > 0) reasons.push("review.blocked.confirm");
  if (rows.length > 0 && blocking === 0 && distinctGenerics < MIN_DISTINCT_DRUGS) reasons.push("review.blocked.min");
  if (patientId === null) reasons.push("review.blocked.patient");
  if (rows.length > 0 && blocking === 0 && !checked) reasons.push("review.blocked.check");

  const canRun = reasons.length === 0 && !starting && patientId !== null;
  const canTick = rows.length > 0 && blocking === 0;

  async function onRun() {
    if (!canRun || patientId === null) return;
    setStarting(true);
    setStartError(null);
    idemKey.current ??= newIdempotencyKey();
    let stage: Stage = "link";
    try {
      const items = rows.flatMap((row) => {
        const res = resolvedOf(row);
        return res ? [{ row, res }] : [];
      });

      // Medicines that still need saving (unchanged ones from an earlier attempt are reused).
      const todo = items.filter(({ row, res }) => saved.current.get(row.id)?.sig !== signature(patientId, row, res.generic));

      // 1. Link every generic to a Drug id BEFORE saving anything: if one cannot be linked, nothing is written.
      const generics = Array.from(new Set(todo.map(({ res }) => res.generic.trim().toLowerCase())));
      const drugIds = new Map<string, number | null>();
      await Promise.all(generics.map(async (g) => void drugIds.set(g, await findDrugId(g))));
      const missing = todo
        .filter(({ res }) => drugIds.get(res.generic.trim().toLowerCase()) == null)
        .map(({ row }) => row.rawText);
      if (missing.length > 0) {
        setStartError({ key: "review.error.noDrug", vars: { names: missing.join(", ") } });
        return;
      }

      // 2. Save to the patient's record, one at a time, remembering each id so a retry never duplicates it.
      stage = "save";
      for (const { row, res } of todo) {
        const med = await addMedication(patientId, {
          raw_text: row.rawText,
          brand_name: res.match_type === "generic" ? "" : res.matched_name,
          strength: row.strength.trim(),
          frequency: row.frequency.trim(),
          drug_id: drugIds.get(res.generic.trim().toLowerCase()) ?? null,
        });
        saved.current.set(row.id, { sig: signature(patientId, row, res.generic), medicationId: med.id });
      }

      const medicationIds: number[] = [];
      for (const { row } of items) {
        const entry = saved.current.get(row.id);
        if (!entry) throw new Error("medicine was not saved");
        medicationIds.push(entry.medicationId);
      }

      // 3. Start the run. The same key is re-sent on a retry of this click, so the server creates one run.
      stage = "start";
      const run = await startAnalysis({
        patient_id: patientId,
        medication_ids: medicationIds,
        idempotency_key: idemKey.current,
      });

      // 4. Live progress.
      navigate(`/analysis/${run.run_id}`);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 409) idemKey.current = null; // key clash: next click gets a fresh key
      setStartError(startErrorFor(err, stage));
    } finally {
      setStarting(false);
    }
  }

  const summary =
    blocking > 0 ? t("review.summary.attention", { n: blocking }) : rows.length > 0 ? t("review.summary.ready") : "";

  return (
    <section>
      <PageHeader title={t("review.title")} subtitle={t("review.hint")} />
      {isSample && <p className="sample-note" role="note">{t("review.sample")}</p>}

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

            {patients === null && !patientsFailed && <p className="muted small" role="status">{t("review.patient.loading")}</p>}

            {patientsFailed && (
              <p className="alert" role="alert">
                {t("review.patient.error")}{" "}
                <button type="button" className="link-btn" onClick={() => void loadPatients()}>{t("common.retry")}</button>
              </p>
            )}

            {patients !== null && patients.length === 0 && (
              <p className="muted small">
                {t("review.patient.empty")} <Link to="/patients">{t("patients.title")}</Link>
              </p>
            )}

            {patients !== null && patients.length > 0 && (
              <label className="field">
                {t("review.patient.label")}
                <select
                  value={patientId ?? ""}
                  disabled={starting}
                  onChange={(e) => {
                    setPatientId(patientIdFrom(e.target.value));
                    touch();
                  }}
                >
                  <option value="">{t("review.patient.placeholder")}</option>
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>{p.patient_code}</option>
                  ))}
                </select>
              </label>
            )}

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

            {startError && <p className="alert" role="alert">{t(startError.key, startError.vars)}</p>}

            <p className="muted small">{t("review.saveNote")}</p>

            <button
              type="button"
              className="btn block"
              disabled={!canRun}
              aria-describedby={reasons.length > 0 ? "run-blocked" : undefined}
              onClick={() => void onRun()}
            >
              {starting ? t("review.running") : t("review.run")}
            </button>
          </div>
        </aside>
      </div>
    </section>
  );
}