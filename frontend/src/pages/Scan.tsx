import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import "../styles/scan.css";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusPill, type Tone } from "../components/ui/StatusPill";
import { useScan, type ScanIssue } from "../hooks/useScan";
import { useI18n, type MessageKey } from "../i18n";
import { ApiRequestError } from "../lib/api";
import { listPatientOptions } from "../lib/clinical";
import { draftsToRows, uploadScan, type ScanStatus } from "../lib/scan";
import type { Patient } from "../lib/types";
import type { ReviewNavState } from "../review";

/** The backend accepts JPEG / PNG / WebP only (decided from the file's bytes there). This is just an early, friendly check. */
const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
/** Backend default SCAN_MAX_UPLOAD_BYTES. If the server's limit differs, its own 413 answer is shown instead. */
const MAX_MB = 8;
const MAX_BYTES = MAX_MB * 1024 * 1024;

/** Backend scan `error_code` values (apps/clinical/runner.py). Anything else falls back to "unknown". */
const FAIL_TEXT: Record<string, MessageKey> = {
  consent_revoked: "scan.fail.consent_revoked",
  image_missing: "scan.fail.image_missing",
  vision_not_configured: "scan.fail.vision_not_configured",
  timeout: "scan.fail.timeout",
  not_a_prescription: "scan.fail.not_a_prescription",
  no_medications_found: "scan.fail.no_medications_found",
  invalid_model_output: "scan.fail.invalid_model_output",
  extraction_failed: "scan.fail.extraction_failed",
  enqueue_failed: "scan.fail.enqueue_failed",
};

const STATUS_TEXT: Record<ScanStatus, MessageKey> = {
  queued: "scan.status.queued",
  processing: "scan.status.processing",
  extracted: "scan.status.preparing",
  failed: "scan.status.failed",
};

const STATUS_TONE: Record<ScanStatus, Tone> = {
  queued: "neutral",
  processing: "neutral",
  extracted: "neutral",
  failed: "stop",
};

const ISSUE_TEXT: Partial<Record<ScanIssue, MessageKey>> = {
  connection: "analysis.poll.connection",
  server: "analysis.poll.server",
  slow: "scan.poll.slow",
};

interface FormError {
  key: MessageKey;
  vars?: Record<string, string | number>;
}

function patientIdFrom(value: unknown): number | null {
  const n = typeof value === "string" ? Number(value) : value;
  return typeof n === "number" && Number.isInteger(n) && n > 0 ? n : null;
}

/** Early checks on the chosen file. The server checks the real bytes again, so this never replaces its answer. */
function checkFile(file: File): FormError | null {
  if (file.size === 0) return { key: "scan.error.empty" };
  if (file.type && !ALLOWED_TYPES.includes(file.type)) return { key: "scan.error.type" };
  if (file.size > MAX_BYTES) return { key: "scan.error.size", vars: { mb: MAX_MB } };
  return null;
}

function errorCode(err: ApiRequestError): string | undefined {
  const top = err.body?.error?.code;
  if (typeof top === "string") return top;
  return (err.body?.error?.details as { code?: string } | undefined)?.code;
}

function uploadErrorFor(err: unknown): FormError {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) return { key: "login.network" };
    const code = errorCode(err);
    if (code === "consent_required") return { key: "scan.error.consent" };
    if (code === "empty_file") return { key: "scan.error.empty" };
    if (err.status === 404) return { key: "scan.error.patient" };
    if (err.status === 413) return { key: "scan.error.size", vars: { mb: MAX_MB } };
    if (err.status === 415) return { key: "scan.error.type" };
    if (err.status === 429) return { key: "scan.error.tooMany" };
    if (err.status >= 500) return { key: "login.server" };
  }
  return { key: "scan.error.upload" };
}

/**
 * Day 8: upload a prescription photo → the server reads it in the background → the draft list is opened on Review & Confirm.
 *
 * Human in the loop (rule.md): what the model read is only ever a DRAFT. This screen never confirms, resolves or analyses
 * anything; it hands the draft rows to the Review screen, where every row is checked by a person.
 *
 * Honest states: upload errors say what to fix (type, size, consent); a failed scan shows its real reason and offers a new
 * try or manual entry; polling problems are reported (never shown as "still working" forever).
 */
export default function Scan() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // ---- patient picker (a patient may be pre-selected with ?patient=ID; it is never guessed) ----
  const [patients, setPatients] = useState<Patient[] | null>(null);
  const [patientsFailed, setPatientsFailed] = useState(false);
  const [patientId, setPatientId] = useState<number | null>(() => patientIdFrom(searchParams.get("patient")));
  const patientsSeq = useRef(0);

  const loadPatients = useCallback(async () => {
    const n = ++patientsSeq.current;
    setPatientsFailed(false);
    try {
      const list = await listPatientOptions();
      if (patientsSeq.current !== n) return;
      setPatients(list);
      setPatientId((cur) => (cur !== null && list.some((p) => p.id === cur) ? cur : null));
    } catch {
      if (patientsSeq.current !== n) return;
      setPatientsFailed(true);
    }
  }, []);

  useEffect(() => {
    void loadPatients();
    return () => {
      patientsSeq.current++;
    };
  }, [loadPatients]);

  // ---- file ----
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const pickRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // ---- upload + watch ----
  const [formError, setFormError] = useState<FormError | null>(null);
  const [uploading, setUploading] = useState(false);
  const [scanId, setScanId] = useState<number | null>(null);
  const [replay, setReplay] = useState(false);
  const [rowsFailed, setRowsFailed] = useState(false);
  const { scan, issue, loading, retry } = useScan(scanId);

  function choose(next: File | null) {
    if (!next) return;
    const problem = checkFile(next);
    if (problem) {
      setFile(null);
      setFormError(problem);
      return;
    }
    setFormError(null);
    setFile(next);
  }

  function onInput(e: ChangeEvent<HTMLInputElement>) {
    choose(e.target.files?.[0] ?? null);
    e.target.value = ""; // the same file can be chosen again after "Choose another image"
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    if (uploading) return;
    choose(e.dataTransfer.files?.[0] ?? null);
  }

  async function onUpload() {
    if (!file || patientId === null || uploading) return;
    setUploading(true);
    setFormError(null);
    try {
      const res = await uploadScan(patientId, file);
      setReplay(res.idempotent_replay);
      setScanId(res.scan_id);
    } catch (err) {
      setFormError(uploadErrorFor(err));
    } finally {
      setUploading(false);
    }
  }

  function startOver() {
    setScanId(null);
    setReplay(false);
    setRowsFailed(false);
    setFile(null);
    setFormError(null);
  }

  // Once the draft list exists: re-check every row with the resolver, then open Review & Confirm with the rows.
  useEffect(() => {
    if (!scan || scan.status !== "extracted") return;
    const drafts = scan.drafts;
    if (!drafts || drafts.length === 0) {
      setRowsFailed(true);
      return;
    }
    let cancelled = false;
    void draftsToRows(drafts).then((rows) => {
      if (cancelled) return;
      const state: ReviewNavState = {
        rows,
        patientId: scan.patient_id,
        scanId: scan.scan_id,
        legibility: scan.legibility ?? "unknown",
      };
      navigate("/review", { state });
    });
    return () => {
      cancelled = true;
    };
  }, [scan, navigate]);

  // ---------------------------------------------------------------------------------------------------------
  // Watching a scan
  // ---------------------------------------------------------------------------------------------------------
  if (scanId !== null) {
    if (issue === "not_found") {
      return (
        <section>
          <PageHeader title={t("scan.title")} />
          <div className="card empty">
            <p role="alert">{t("scan.notFound")}</p>
            <button type="button" className="btn" onClick={startOver}>{t("scan.startOver")}</button>
          </div>
        </section>
      );
    }

    const status = scan?.status ?? null;
    const failed = status === "failed" || rowsFailed;
    const inFlight = status === "queued" || status === "processing" || status === "extracted";
    // Once we have given up polling the last known status may be stale: no moving bar.
    const gaveUp = issue === "connection" || issue === "server" || issue === "slow";
    const showBar = inFlight && !gaveUp && !failed;

    let message: string | null = null;
    if (failed) message = t(FAIL_TEXT[rowsFailed ? "no_medications_found" : (scan?.error_code ?? "")] ?? "scan.fail.unknown");
    else if (status === "queued") message = t("scan.hint.queued");
    else if (status === "processing") message = t("scan.hint.processing");
    else if (status === "extracted") message = t("scan.hint.preparing");

    const issueKey = issue ? ISSUE_TEXT[issue] : undefined;
    const pillStatus: ScanStatus = failed ? "failed" : (status ?? "queued");

    return (
      <section>
        <PageHeader title={t("scan.title")} subtitle={t("scan.hint")} />

        {loading && (
          <div className="card" aria-busy="true">
            <p className="muted" role="status">{t("common.loading")}</p>
            <div className="skeleton run-skeleton" aria-hidden="true" />
          </div>
        )}

        {scan && (
          <div className="card scan-status">
            <div className="scan-status-head">
              <StatusPill tone={STATUS_TONE[pillStatus]}>{t(STATUS_TEXT[pillStatus])}</StatusPill>
            </div>

            {showBar && (
              <div className="scan-bar" role="progressbar" aria-label={t("scan.progress.label")}>
                <span />
              </div>
            )}

            <div role="status" aria-live="polite">
              {message && (failed ? <p className="alert scan-alert">{message}</p> : <p>{message}</p>)}
            </div>

            {replay && !failed && <p className="muted small">{t("scan.replay")}</p>}

            {issue === "reconnecting" && <p className="muted small" role="status">{t("analysis.poll.reconnecting")}</p>}

            {issueKey && (
              <p className="alert scan-alert" role="alert">
                {t(issueKey)}{" "}
                <button type="button" className="link-btn" onClick={retry}>{t("common.retry")}</button>
              </p>
            )}

            {failed && (
              <div className="scan-actions">
                <button type="button" className="btn" onClick={startOver}>{t("scan.startOver")}</button>
                <Link to="/medications" className="btn secondary">{t("scan.manual")}</Link>
              </div>
            )}
          </div>
        )}
      </section>
    );
  }

  // ---------------------------------------------------------------------------------------------------------
  // Choosing the image
  // ---------------------------------------------------------------------------------------------------------
  const noPatients = patients !== null && patients.length === 0;
  const canUpload = file !== null && patientId !== null && !uploading;
  const hint = patientId === null ? t("scan.need.patient") : file === null ? t("scan.need.file") : "";
  const sizeLabel = file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` : "";

  return (
    <section>
      <PageHeader
        title={t("scan.title")}
        subtitle={t("scan.hint")}
        actions={<Link to="/medications" className="btn secondary">{t("scan.manual")}</Link>}
      />

      <div className="scan-grid">
        <div className="card">
          <h2>{t("scan.patient.label")}</h2>

          {patients === null && !patientsFailed && <p className="muted small" role="status">{t("scan.patient.loading")}</p>}

          {patientsFailed && (
            <p className="alert" role="alert">
              {t("scan.patient.error")}{" "}
              <button type="button" className="link-btn" onClick={() => void loadPatients()}>{t("common.retry")}</button>
            </p>
          )}

          {noPatients && (
            <p className="muted small">
              {t("scan.patient.empty")} <Link to="/patients">{t("patients.title")}</Link>
            </p>
          )}

          {patients !== null && patients.length > 0 && (
            <label className="field">
              {t("scan.patient.label")}
              <select
                value={patientId ?? ""}
                disabled={uploading}
                onChange={(e) => {
                  setPatientId(patientIdFrom(e.target.value));
                  setFormError(null);
                }}
              >
                <option value="">{t("scan.patient.placeholder")}</option>
                {patients.map((p) => (
                  <option key={p.id} value={p.id}>{p.patient_code}</option>
                ))}
              </select>
            </label>
          )}

          <p className="muted small scan-privacy">{t("scan.privacy")}</p>
        </div>

        <div className="card">
          <h2>{t("scan.photo.title")}</h2>

          {/* Both inputs are hidden and driven by real buttons, so keyboard and screen-reader users get normal controls. */}
          <input ref={pickRef} type="file" accept={ALLOWED_TYPES.join(",")} hidden onChange={onInput} />
          <input ref={cameraRef} type="file" accept={ALLOWED_TYPES.join(",")} capture="environment" hidden onChange={onInput} />

          {file && previewUrl ? (
            <div className="scan-preview">
              <img src={previewUrl} alt={t("scan.preview.alt")} />
              <p className="small muted">{file.name} · {sizeLabel}</p>
            </div>
          ) : (
            <div
              className={`dropzone${dragging ? " is-dragging" : ""}`}
              role="group"
              aria-label={t("scan.photo.title")}
              onDragOver={(e) => {
                e.preventDefault();
                if (!uploading) setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <p className="muted">{t("scan.drop")}</p>
              <p className="muted small">{t("scan.formats", { mb: MAX_MB })}</p>
            </div>
          )}

          <div className="scan-actions">
            <button type="button" className="btn secondary" disabled={uploading} onClick={() => cameraRef.current?.click()}>
              {t("scan.camera")}
            </button>
            <button type="button" className="btn secondary" disabled={uploading} onClick={() => pickRef.current?.click()}>
              {file ? t("scan.change") : t("scan.choose")}
            </button>
          </div>

          {formError && <p className="alert scan-form-error" role="alert">{t(formError.key, formError.vars)}</p>}

          <div className="scan-submit">
            <button
              type="button"
              className="btn block"
              disabled={!canUpload}
              aria-describedby={hint ? "scan-hint" : undefined}
              onClick={() => void onUpload()}
            >
              {uploading ? t("scan.uploading") : t("scan.upload")}
            </button>
            {hint && <p id="scan-hint" className="muted small">{hint}</p>}
          </div>
        </div>
      </div>
    </section>
  );
}