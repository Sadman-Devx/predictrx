import { Link } from "react-router-dom";
import "../styles/family.css";
import { PageHeader } from "../components/ui/PageHeader";
import { useFamilyList } from "../hooks/useFamily";
import { useI18n } from "../i18n";

/**
 * Family view, step 1 (Day 9, NRB): the patients that a doctor has shared with the signed-in family member.
 * Read-only. A patient appears here only while the server reports an active family link AND an active consent.
 */
export default function Family() {
  const { t } = useI18n();
  const { patients, state, retry } = useFamilyList();

  return (
    <section>
      <PageHeader title={t("family.title")} subtitle={t("family.subtitle")} />

      {state === "loading" && (
        <div className="card" aria-busy="true">
          <p className="muted" role="status">{t("common.loading")}</p>
        </div>
      )}

      {state === "error" && (
        <div className="card empty">
          <p className="alert" role="alert">{t("family.list.error")}</p>
          <button type="button" className="btn" onClick={retry}>{t("common.retry")}</button>
        </div>
      )}

      {state === "ready" && patients.length === 0 && (
        <div className="card empty">
          <p>{t("family.list.empty")}</p>
        </div>
      )}

      {state === "ready" && patients.length > 0 && (
        <>
          <h2>{t("family.list.title")}</h2>
          <ul className="patient-grid">
            {patients.map((p) => (
              <li key={p.id}>
                <Link to={`/family/${p.id}`} className="patient-card">
                  <span className="patient-code">{p.patient_code || `#${p.id}`}</span>
                  {p.relationship && <span className="patient-meta">{t("family.relationship", { r: p.relationship })}</span>}
                  <span className="patient-meta">{t("family.open")}</span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}