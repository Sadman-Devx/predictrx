import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/ui/Icon";
import { useI18n, type MessageKey } from "../i18n";
import { formatWhen } from "../lib/format";
import { getDashboardSummary } from "../lib/dashboard";
import type { DashboardActivityType, DashboardSummary } from "../lib/types";
import "../styles/dashboard.css";

const ACTIVITY_LABELS: Record<DashboardActivityType, MessageKey> = {
  analysis_run: "dashboard.activity.analysisRun",
  patient_opened: "dashboard.activity.patientOpened",
  family_viewed: "dashboard.activity.familyViewed",
  consent_granted: "dashboard.activity.consentGranted",
  consent_revoked: "dashboard.activity.consentRevoked",
  consent_changed: "dashboard.activity.consentChanged",
};

export default function Dashboard() {
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setFailed(false);
    try {
      setSummary(await getDashboardSummary(signal));
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

  const locale = lang === "bn" ? "bn-BD" : "en-GB";
  const number = new Intl.NumberFormat(locale);
  const today = new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date());
  const displayName = user?.display_name.trim() || t("dashboard.roleFallback");

  return (
    <section className="dashboard-page" aria-labelledby="dashboard-title">
      <header className="card dashboard-welcome">
        <div className="dashboard-welcome-copy">
          <p className="dashboard-date">{today}</p>
          <h1 id="dashboard-title">{t("dashboard.greeting", { name: displayName })}</h1>
          <p className="muted">{t("dashboard.subtitle")}</p>
        </div>
        <Link to="/scan" className="btn">
          <Icon name="plus" />
          {t("dashboard.cta")}
        </Link>
      </header>

      {failed && (
        <div className="alert dashboard-error" role="alert">
          {t("dashboard.error")}{" "}
          <button type="button" className="link-btn" onClick={() => void load()}>
            {t("common.retry")}
          </button>
        </div>
      )}

      {loading && !summary && <p className="muted" role="status" aria-busy="true">{t("common.loading")}</p>}

      {summary && (
        <>
          <div className="dashboard-metrics" aria-label={t("dashboard.metrics")}>
            <article className="card dashboard-stat">
              <span className="dashboard-stat-icon"><Icon name="patients" /></span>
              <p className="dashboard-stat-label">{t("dashboard.totalPatients")}</p>
              <strong className="dashboard-stat-value">{number.format(summary.total_patients)}</strong>
            </article>
            <article className="card dashboard-stat">
              <span className="dashboard-stat-icon"><Icon name="analyses" /></span>
              <p className="dashboard-stat-label">{t("dashboard.totalAnalyses")}</p>
              <strong className="dashboard-stat-value">{number.format(summary.total_analyses)}</strong>
            </article>
            <article className="card dashboard-stat">
              <span className="dashboard-stat-icon"><Icon name="scan" /></span>
              <p className="dashboard-stat-label">{t("dashboard.pendingReviews")}</p>
              <strong className="dashboard-stat-value">{number.format(summary.pending_reviews)}</strong>
            </article>
            {(user?.role === "doctor" || user?.role === "pharmacist") && (
              <>
                <Link to="/follow-ups" className="card dashboard-stat dashboard-stat-link">
                  <span className="dashboard-stat-icon"><Icon name="shield-check" /></span>
                  <span className="dashboard-stat-label">{t("dashboard.pendingFollowups")}</span>
                  <strong className="dashboard-stat-value">{number.format(summary.pending_followups)}</strong>
                </Link>
                <Link to="/follow-ups" className="card dashboard-stat dashboard-stat-link">
                  <span className="dashboard-stat-icon dashboard-stat-icon-overdue"><Icon name="shield-off" /></span>
                  <span className="dashboard-stat-label">{t("dashboard.overdueFollowups")}</span>
                  <strong className="dashboard-stat-value">{number.format(summary.overdue_followups)}</strong>
                </Link>
              </>
            )}
          </div>

          <div className="dashboard-panels">
            <section className="card dashboard-panel" aria-labelledby="dashboard-patients-title">
              <h2 id="dashboard-patients-title">{t("dashboard.recentPatients")}</h2>
              {summary.recent_patients.length === 0 ? (
                <p className="muted dashboard-empty">{t("dashboard.noPatients")}</p>
              ) : (
                <ul className="dashboard-patient-list">
                  {summary.recent_patients.map((patient) => (
                    <li key={patient.id}>
                      <Link to={`/patients/${patient.id}`} className="dashboard-patient">
                        <span className="dashboard-patient-copy">
                          <strong>{patient.patient_code}</strong>
                          <span className="muted small">
                            {t("dashboard.medications", { count: number.format(patient.medication_count) })}
                          </span>
                        </span>
                        <Icon name="arrow-left" />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <Link to="/patients" className="dashboard-view-all">{t("dashboard.viewAllPatients")}</Link>
            </section>

            <section className="card dashboard-panel" aria-labelledby="dashboard-activity-title">
              <h2 id="dashboard-activity-title">{t("dashboard.activityTitle")}</h2>
              {summary.recent_activity.length === 0 ? (
                <p className="muted dashboard-empty">{t("dashboard.noActivity")}</p>
              ) : (
                <ol className="dashboard-timeline">
                  {summary.recent_activity.map((activity) => (
                    <li key={activity.id} className="dashboard-timeline-item">
                      <span className="dashboard-timeline-dot" aria-hidden="true" />
                      <div className="dashboard-activity">
                        <strong>
                          {t(ACTIVITY_LABELS[activity.event])} · {activity.patient_code}
                        </strong>
                        <time className="muted small" dateTime={activity.at}>{formatWhen(activity.at, lang)}</time>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        </>
      )}
    </section>
  );
}
