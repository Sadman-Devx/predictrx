import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { useI18n } from "../i18n";
import { listAnalyses } from "../lib/analysis";
import { formatWhen } from "../lib/format";
import type { AnalysisListItem } from "../lib/types";
import "../styles/analysis.css";
import "../styles/profile.css";

/**
 * Route: /twin. The what-if simulation always starts from a finished analysis and never changes it, so this page
 * lists the clinician's completed runs; each one opens straight on its What-if tab (/analysis/:id?tab=twin).
 */
export default function TwinHome() {
  const { t, lang } = useI18n();
  const [items, setItems] = useState<AnalysisListItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    try {
      setItems((await listAnalyses(1, "completed")).results);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section>
      <PageHeader title={t("twin.title")} />
      <p className="muted">{t("twin.home.hint")}</p>

      {failed && (
        <div className="alert" role="alert">
          {t("twin.home.error")}{" "}
          <button type="button" className="link-btn" onClick={() => void load()}>{t("common.retry")}</button>
        </div>
      )}
      {!items && !failed && <p className="muted" aria-busy="true">{t("common.loading")}</p>}

      {items && items.length === 0 && (
        <div className="card empty">
          <p>{t("twin.home.empty")}</p>
          <Link to="/scan" className="btn">{t("dashboard.cta")}</Link>
        </div>
      )}

      {items && items.length > 0 && (
        <>
          <h2 className="profile-h">{t("twin.home.pick")}</h2>
          <ul className="analysis-list">
            {items.map((r) => (
              <li key={r.run_id} className="card analysis-row">
                <div className="analysis-row-main">
                  <strong>{t("analysis.run.title", { id: r.run_id })}</strong>
                  <span className="muted small">
                    {t("analysisList.patient")}: {r.patient_code} · {t("analysisList.medicines", { n: r.medication_count })}
                  </span>
                  {r.finished_at && <span className="muted small">{formatWhen(r.finished_at, lang)}</span>}
                </div>
                <Link to={`/analysis/${r.run_id}?tab=twin`} className="btn">{t("twin.home.open")}</Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
