import { Link, useParams } from "react-router-dom";
import { PipelineStepper } from "../components/analysis/PipelineStepper";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusPill, type Tone } from "../components/ui/StatusPill";
import { useAnalysisRun, type PollIssue } from "../hooks/useAnalysisRun";
import { useI18n, type MessageKey } from "../i18n";
import { deriveSteps } from "../lib/analysis";
import type { RunStatus } from "../lib/types";

const STATUS_TEXT: Record<RunStatus, MessageKey> = {
  queued: "analysis.status.queued",
  running: "analysis.status.running",
  completed: "analysis.status.completed",
  failed: "analysis.status.failed",
};

// "completed" means the pipeline finished, not that the medicines are safe: the wording below never says safe.
const STATUS_TONE: Record<RunStatus, Tone> = {
  queued: "neutral",
  running: "neutral",
  completed: "ok",
  failed: "stop",
};

/** Backend `error_code` values (apps/analysis/runner.py + services.py). Anything else falls back to "unknown". */
const ERROR_TEXT: Record<string, MessageKey> = {
  timeout: "analysis.error.timeout",
  pipeline_unavailable: "analysis.error.pipeline_unavailable",
  malformed_finding: "analysis.error.malformed_finding",
  pipeline_error: "analysis.error.pipeline_error",
  enqueue_failed: "analysis.error.enqueue_failed",
};

const ISSUE_TEXT: Partial<Record<PollIssue, MessageKey>> = {
  connection: "analysis.poll.connection",
  server: "analysis.poll.server",
  slow: "analysis.poll.slow",
};

/** Route: /analysis/:runId. Keyed by the id so moving between runs starts a fresh watch. */
export default function AnalysisRun() {
  const { runId } = useParams();
  return <RunView key={runId ?? ""} runId={Number(runId)} />;
}

function RunView({ runId }: { runId: number }) {
  const { t } = useI18n();
  const { run, trace, traceKnown, issue, loading, retry } = useAnalysisRun(runId);

  if (issue === "not_found") {
    return (
      <section>
        <PageHeader title={t("analysis.run.title", { id: Number.isFinite(runId) ? runId : "?" })} />
        <div className="card empty">
          <p role="alert">{t("analysis.notFound")}</p>
          <Link to="/scan" className="btn">{t("dashboard.cta")}</Link>
        </div>
      </section>
    );
  }

  const status = run?.status ?? null;
  const inFlight = status === "queued" || status === "running";
  // Once we have given up polling, the last known status may be stale: no moving bar.
  const gaveUp = issue === "connection" || issue === "server" || issue === "slow";
  const showBar = inFlight && !gaveUp;
  const steps = deriveSteps(status ?? "queued", trace);

  let message: string | null = null;
  let failed = false;
  if (run) {
    if (run.status === "queued") message = t("analysis.hint.queued");
    else if (run.status === "running") message = t("analysis.hint.running");
    else if (run.status === "completed") {
      const n = run.findings_count;
      if (n === 0) message = t("analysis.done.none"); // never a "safe" statement
      else if (n === 1) message = t("analysis.done.one");
      else if (n !== null) message = t("analysis.done.count", { n });
    } else {
      failed = true;
      message = t(ERROR_TEXT[run.error_code ?? ""] ?? "analysis.error.unknown");
    }
  }

  const issueKey = issue ? ISSUE_TEXT[issue] : undefined;

  return (
    <section>
      <PageHeader title={t("analysis.run.title", { id: runId })} subtitle={t("analysis.run.subtitle")} />

      {loading && (
        <div className="card" aria-busy="true">
          <p className="muted" role="status">{t("common.loading")}</p>
          <div className="skeleton run-skeleton" aria-hidden="true" />
        </div>
      )}

      {run && (
        <div className="card run-status">
          <div className="run-status-head">
            <StatusPill tone={STATUS_TONE[run.status]}>{t(STATUS_TEXT[run.status])}</StatusPill>
            <span className="muted small">
              {t(run.medication_count === 1 ? "patients.medicines.one" : "patients.medicines", { n: run.medication_count })}
            </span>
          </div>

          {showBar && (
            <div className="run-bar" role="progressbar" aria-label={t("analysis.progress.label")}>
              <span />
            </div>
          )}

          {/* aria-live: a screen-reader user hears the change from "in progress" to "complete" / "failed". */}
          <div role="status" aria-live="polite">
            {message && (failed ? <p className="alert run-alert">{message}</p> : <p>{message}</p>)}
          </div>

          {issue === "reconnecting" && <p className="muted small" role="status">{t("analysis.poll.reconnecting")}</p>}

          {issueKey && (
            <p className="alert run-alert" role="alert">
              {t(issueKey)}{" "}
              <button type="button" className="link-btn" onClick={retry}>{t("common.retry")}</button>
            </p>
          )}

          {run.status === "completed" && <p className="muted small">{t("analysis.done.detailsSoon")}</p>}

          {(run.status === "completed" || run.status === "failed") && (
            <div className="run-actions">
              {run.status === "completed" && (
                <Link to={`/patients/${run.patient_id}`} className="btn secondary">{t("analysis.done.patient")}</Link>
              )}
              {run.status === "failed" && <Link to="/scan" className="btn">{t("dashboard.cta")}</Link>}
            </div>
          )}
        </div>
      )}

      {run && (
        <div className="card">
          <PipelineStepper steps={steps} />
          {run.status === "completed" && !traceKnown && (
            <p className="muted small run-trace-note">{t("analysis.trace.unavailable")}</p>
          )}
        </div>
      )}
    </section>
  );
}