import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useI18n, type MessageKey } from "../../i18n";
import { getPatientAnalysisHistory } from "../../lib/clinical";
import type { PatientAnalysisHistoryRun, Severity } from "../../lib/types";
import "../../styles/patient-history.css";

const SEVERITIES: Array<{ key: Severity; label: MessageKey; className: string }> = [
  { key: "major", label: "severity.major", className: "patient-history-segment-major" },
  { key: "moderate", label: "severity.moderate", className: "patient-history-segment-moderate" },
  { key: "minor", label: "severity.minor", className: "patient-history-segment-minor" },
  { key: "unknown", label: "severity.unknown", className: "patient-history-segment-unknown" },
];

function formattedDate(value: string | null, lang: "bn" | "en"): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

export function PatientSafetyHistory({ patientId }: { patientId: number }) {
  const { lang, t } = useI18n();
  const [runs, setRuns] = useState<PatientAnalysisHistoryRun[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getPatientAnalysisHistory(patientId)
      .then((history) => {
        if (!active) return;
        setRuns(history.results);
        setTotalCount(history.total_count);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [patientId, retry]);

  const maxFindings = Math.max(0, ...runs.map((run) => run.findings_count));

  return (
    <section className="card patient-history" aria-labelledby="patient-history-title">
      <header className="patient-history-header">
        <div>
          <p className="patient-history-eyebrow">{t("patients.history.eyebrow")}</p>
          <h2 id="patient-history-title">{t("patients.history.title")}</h2>
        </div>
        {!loading && !error && totalCount > 0 && (
          <span className="patient-history-count">{t("patients.history.total", { n: totalCount })}</span>
        )}
      </header>

      <p className="patient-history-note">{t("patients.history.note")}</p>

      {loading ? (
        <p className="muted" role="status">{t("common.loading")}</p>
      ) : error ? (
        <div className="patient-history-error" role="alert">
          <span>{t("patients.history.error")}</span>
          <button type="button" className="btn btn-small" onClick={() => setRetry((value) => value + 1)}>
            {t("common.retry")}
          </button>
        </div>
      ) : runs.length === 0 ? (
        <p className="muted patient-history-empty">{t("patients.history.empty")}</p>
      ) : (
        <>
          {totalCount > runs.length && (
            <p className="patient-history-range">
              {t("patients.history.range", { shown: runs.length, total: totalCount })}
            </p>
          )}
          <div className="patient-history-legend" aria-label={t("patients.history.severityLegend")}>
            {SEVERITIES.map(({ key, label, className }) => (
              <span className="patient-history-legend-item" key={key}>
                <i className={className} aria-hidden="true" />
                {t(label)}
              </span>
            ))}
          </div>
          <ol className="patient-history-list">
            {runs.map((run) => {
              const date = formattedDate(run.occurred_at, lang);
              const accessibleSummary = t("patients.history.openRun", {
                date,
                medicines: run.medication_count,
                findings: run.findings_count,
              });
              return (
                <li className="patient-history-item" key={run.run_id}>
                  <Link to={`/analysis/${run.run_id}`} className="patient-history-run" aria-label={accessibleSummary}>
                    <span className="patient-history-marker" aria-hidden="true" />
                    <div className="patient-history-run-main">
                      <div className="patient-history-run-heading">
                        <time dateTime={run.occurred_at ?? undefined}>{date}</time>
                        <span className="patient-history-run-link">{t("patients.history.open")}</span>
                      </div>
                      <div className="patient-history-run-meta">
                        <span>{t("patients.history.medicines", { n: run.medication_count })}</span>
                        <span>{t("patients.history.findings", { n: run.findings_count })}</span>
                      </div>
                      <div className="patient-history-bar" aria-hidden="true">
                        {SEVERITIES.map(({ key, className }) => {
                          const count = run.severity_counts[key];
                          const width = maxFindings ? (count / maxFindings) * 100 : 0;
                          return count > 0 ? (
                            <span
                              className={className}
                              key={key}
                              style={{ width: `${width}%` }}
                            />
                          ) : null;
                        })}
                      </div>
                      <p className="patient-history-verification">
                        {t("patients.history.verification", {
                          verified: run.verification_counts.verified,
                          unverified: run.verification_counts.unverified,
                          conflict: run.verification_counts.conflict,
                        })}
                      </p>
                    </div>
                    <span className="patient-history-arrow" aria-hidden="true">→</span>
                  </Link>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </section>
  );
}
