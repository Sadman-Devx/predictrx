import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { ToneGlyph, type Tone } from "../components/ui/StatusPill";
import { useI18n, type MessageKey } from "../i18n";
import {
  MAX_PATIENTS,
  REASON_ORDER,
  STALE_DAYS,
  buildQueue,
  loadQueueData,
  type QueueData,
  type QueueRow,
  type Reason,
  type ReasonKind,
} from "../lib/reviewqueue";
import "../styles/reviewqueue.css";

const REASON_TEXT: Record<ReasonKind, MessageKey> = {
  conflict: "rq.reason.conflict",
  major: "rq.reason.major",
  overdue: "rq.reason.overdue",
  unverified: "rq.reason.unverified",
  moderate: "rq.reason.moderate",
  noAnalysis: "rq.reason.noAnalysis",
  stale: "rq.reason.stale",
  openFollowup: "rq.reason.openFollowup",
  noConsent: "rq.reason.noConsent",
};

const RULE_TEXT: Record<ReasonKind, MessageKey> = {
  conflict: "rq.rule.conflict",
  major: "rq.rule.major",
  overdue: "rq.rule.overdue",
  unverified: "rq.rule.unverified",
  moderate: "rq.rule.moderate",
  noAnalysis: "rq.rule.noAnalysis",
  stale: "rq.rule.stale",
  openFollowup: "rq.rule.openFollowup",
  noConsent: "rq.rule.noConsent",
};

// Shape + text + colour: a reason is never shown by colour alone.
const TONE: Record<ReasonKind, Tone> = {
  conflict: "stop",
  major: "stop",
  overdue: "warn",
  unverified: "warn",
  moderate: "warn",
  noAnalysis: "neutral",
  stale: "neutral",
  openFollowup: "neutral",
  noConsent: "neutral",
};

function ReasonChip({ reason }: { reason: Reason }) {
  const { t } = useI18n();
  return (
    <li className={`rq-reason rq-reason-${reason.kind}`}>
      <ToneGlyph tone={TONE[reason.kind]} />
      <span>{t(REASON_TEXT[reason.kind], { n: reason.n ?? 0, days: reason.days ?? 0 })}</span>
    </li>
  );
}

function Row({ row }: { row: QueueRow }) {
  const { t, lang } = useI18n();
  const number = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB");
  const meds = row.patient.medication_count;
  return (
    <li className="card rq-row">
      <div className="rq-row-head">
        <strong>{row.patient.patient_code}</strong>
        {meds != null && (
          <span className="muted small">
            {t(meds === 1 ? "patients.medicines.one" : "patients.medicines", { n: number.format(meds) })}
          </span>
        )}
      </div>
      {row.reasons.length > 0 && (
        <ul className="rq-reasons" aria-label={t("rq.reasons.label")}>
          {row.reasons.map((r) => (
            <ReasonChip key={r.kind} reason={r} />
          ))}
        </ul>
      )}
      <div className="rq-links">
        <Link to={`/patients/${row.patient.id}`} className="btn secondary">{t("rq.open.patient")}</Link>
        {row.latestRunId != null && (
          <Link to={`/analysis/${row.latestRunId}`} className="btn secondary">{t("rq.open.analysis")}</Link>
        )}
      </div>
    </li>
  );
}

/**
 * Route: /review-queue. A suggested order to look at patients in, from plain rules (listed on the page).
 * Not a clinical priority and not a safety statement; a patient with no flag has not been shown to be safe.
 */
export default function ReviewQueue() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<QueueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setFailed(false);
    try {
      setData(await loadQueueData(signal));
    } catch {
      if (!signal?.aborted) setFailed(true);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const queue = useMemo(
    () => (data ? buildQueue(data.patients, data.histories, data.followUps, new Date()) : null),
    [data],
  );
  const number = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB");
  const failedRows = data ? data.patients.filter((p) => data.failedPatientIds.includes(p.id)) : [];
  // A patient whose analysis history could not be read must not look "clear": it is listed separately.
  const flagged = queue ? queue.flagged.filter((r) => !data?.failedPatientIds.includes(r.patient.id)) : [];
  const clear = queue ? queue.clear.filter((r) => !data?.failedPatientIds.includes(r.patient.id)) : [];

  return (
    <section className="rq-page">
      <PageHeader title={t("rq.title")} subtitle={t("rq.subtitle")} />

      <div className="card rq-note" role="note">
        <p>{t("rq.note")}</p>
        <details>
          <summary>{t("rq.rules.title")}</summary>
          <p className="muted small">{t("rq.rules.intro")}</p>
          <ol className="rq-rules">
            {REASON_ORDER.map((k) => (
              <li key={k}>{t(RULE_TEXT[k], { days: STALE_DAYS })}</li>
            ))}
          </ol>
        </details>
      </div>

      {loading && !data && <p className="muted" role="status" aria-busy="true">{t("common.loading")}</p>}

      {failed && (
        <div className="alert" role="alert">
          {t("rq.error")}{" "}
          <button type="button" className="link-btn" onClick={() => void load()}>{t("common.retry")}</button>
        </div>
      )}

      {data && queue && (
        <>
          {data.followUps == null && <p className="alert" role="alert">{t("rq.warn.followups")}</p>}
          {data.totalPatients > MAX_PATIENTS && (
            <p className="muted small" role="note">{t("rq.warn.capped", { shown: MAX_PATIENTS, total: number.format(data.totalPatients) })}</p>
          )}
          {failedRows.length > 0 && (
            <div className="card notice" role="alert">
              <p>{t("rq.warn.failed", { n: failedRows.length })}</p>
              <p className="muted small">{failedRows.map((p) => p.patient_code).join(", ")}</p>
              <button type="button" className="link-btn" onClick={() => void load()}>{t("common.retry")}</button>
            </div>
          )}

          <p aria-live="polite">
            {t("rq.summary", { flagged: number.format(flagged.length), clear: number.format(clear.length) })}
          </p>

          {data.patients.length === 0 ? (
            <div className="card empty"><p>{t("rq.empty")}</p></div>
          ) : (
            <>
              {flagged.length > 0 && (
                <ol className="rq-list" aria-label={t("rq.title")}>
                  {flagged.map((row) => (
                    <Row key={row.patient.id} row={row} />
                  ))}
                </ol>
              )}

              {clear.length > 0 && (
                <details className="card rq-clear">
                  <summary>{t("rq.clear.title", { n: number.format(clear.length) })}</summary>
                  <p className="muted small">{t("rq.clear.hint")}</p>
                  <ul className="rq-clear-list">
                    {clear.map((row) => (
                      <li key={row.patient.id}>
                        <Link to={`/patients/${row.patient.id}`}>{row.patient.patient_code}</Link>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
