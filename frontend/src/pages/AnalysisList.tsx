import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusPill, type Tone } from "../components/ui/StatusPill";
import { useI18n, type MessageKey } from "../i18n";
import { listAnalyses } from "../lib/analysis";
import { formatWhen } from "../lib/format";
import type { AnalysisListItem, Paginated, RunStatus } from "../lib/types";
import "../styles/analysis.css";

const PAGE_SIZE = 20; // backend PAGE_SIZE

const STATUS_TEXT: Record<RunStatus, MessageKey> = {
  queued: "analysis.status.queued",
  running: "analysis.status.running",
  completed: "analysis.status.completed",
  failed: "analysis.status.failed",
};
// "completed" means the pipeline finished, never that the medicines are safe.
const STATUS_TONE: Record<RunStatus, Tone> = { queued: "neutral", running: "neutral", completed: "ok", failed: "stop" };
const FILTERS: (RunStatus | "all")[] = ["all", "completed", "running", "queued", "failed"];

/** Route: /analysis. Past runs of the signed-in clinician; each row opens /analysis/:runId. */
export default function AnalysisList() {
  const { t, lang } = useI18n();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<RunStatus | "all">("all");
  const [data, setData] = useState<Paginated<AnalysisListItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async (p: number, f: RunStatus | "all") => {
    setLoading(true);
    setFailed(false);
    try {
      setData(await listAnalyses(p, f === "all" ? undefined : f));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(page, filter);
  }, [load, page, filter]);

  const items = data?.results ?? [];
  const totalPages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  return (
    <section>
      <PageHeader
        title={t("analysis.title")}
        actions={(
          <>
            <Link to="/twin" className="btn secondary">{t("nav.twin")}</Link>{" "}
            <Link to="/scan" className="btn">{t("dashboard.cta")}</Link>
          </>
        )}
      />

      <div className="card toolbar">
        <div className="chips" role="group" aria-label={t("analysisList.filter.label")}>
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              className="chip"
              aria-pressed={filter === f}
              onClick={() => { setFilter(f); setPage(1); }}
            >
              {f === "all" ? t("analysisList.filter.all") : t(STATUS_TEXT[f])}
            </button>
          ))}
        </div>
      </div>

      {failed && (
        <div className="alert" role="alert">
          {t("analysisList.error")}{" "}
          <button type="button" className="link-btn" onClick={() => void load(page, filter)}>{t("common.retry")}</button>
        </div>
      )}

      {loading && !data && <p className="muted" aria-busy="true">{t("common.loading")}</p>}

      {data && items.length === 0 && !failed && (
        <div className="card empty">
          <p>{t("analysisList.empty")}</p>
          <Link to="/scan" className="btn">{t("dashboard.cta")}</Link>
        </div>
      )}

      {items.length > 0 && (
        <ul className="analysis-list" aria-busy={loading}>
          {items.map((r) => (
            <li key={r.run_id} className="card analysis-row">
              <div className="analysis-row-main">
                <strong>{t("analysis.run.title", { id: r.run_id })}</strong>
                <span className="muted small">
                  {t("analysisList.patient")}: {r.patient_code} · {t("analysisList.medicines", { n: r.medication_count })}
                  {r.status === "completed" && <> · {t("analysisList.findings", { n: r.findings_count })}</>}
                </span>
                {r.started_at && (
                  <span className="muted small">{t("analysisList.started")}: {formatWhen(r.started_at, lang)}</span>
                )}
              </div>
              <StatusPill tone={STATUS_TONE[r.status]}>{t(STATUS_TEXT[r.status])}</StatusPill>
              <Link to={`/analysis/${r.run_id}`} className="btn secondary">{t("analysisList.open")}</Link>
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <nav className="pager" aria-label={t("analysisList.page", { page, pages: totalPages })}>
          <button type="button" className="btn secondary" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>
            {t("analysisList.prev")}
          </button>
          <span className="muted small">{t("analysisList.page", { page, pages: totalPages })}</span>
          <button type="button" className="btn secondary" disabled={page >= totalPages || loading} onClick={() => setPage(page + 1)}>
            {t("analysisList.next")}
          </button>
        </nav>
      )}
    </section>
  );
}
