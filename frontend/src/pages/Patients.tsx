import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PatientForm } from "../components/patient/PatientForm";
import { Icon } from "../components/ui/Icon";
import { PageHeader } from "../components/ui/PageHeader";
import { useI18n, type MessageKey } from "../i18n";
import { listPatients } from "../lib/clinical";
import type { Paginated, Patient } from "../lib/types";

const SEX_KEY: Record<string, MessageKey> = {
  male: "patients.sex.male",
  female: "patients.sex.female",
  other: "patients.sex.other",
};

type Filter = "all" | "consent" | "noConsent";

const FILTERS: { value: Filter; key: MessageKey }[] = [
  { value: "all", key: "patients.filter.all" },
  { value: "consent", key: "patients.filter.consent" },
  { value: "noConsent", key: "patients.filter.noConsent" },
];

const PAGE_SIZE = 20; // backend PAGE_SIZE

export default function Patients() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<Patient> | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const load = useCallback(async (p: number) => {
    setLoading(true);
    setFailed(false);
    try {
      setData(await listPatients(p));
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(page);
  }, [load, page]);

  const items = data?.results ?? [];
  // The consent filters only make sense when the server actually reports consent. Never faked.
  const hasConsentData = items.some((p) => typeof p.consent_active === "boolean");
  const activeFilter: Filter = hasConsentData ? filter : "all";

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((p) => {
      if (q && !p.patient_code.toLowerCase().includes(q)) return false;
      if (activeFilter === "consent") return p.consent_active === true;
      if (activeFilter === "noConsent") return p.consent_active === false;
      return true;
    });
  }, [items, query, activeFilter]);

  const totalPages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;
  const year = new Date().getFullYear();

  function meta(p: Patient): string {
    const parts: string[] = [];
    if (p.birth_year) parts.push(t("patients.age", { n: year - p.birth_year }));
    if (p.sex && SEX_KEY[p.sex]) parts.push(t(SEX_KEY[p.sex]));
    const w = p.weight_kg !== null && p.weight_kg !== "" ? Number(p.weight_kg) : NaN;
    if (Number.isFinite(w)) parts.push(t("patients.kg", { n: w }));
    return parts.join(" · ");
  }

  return (
    <section>
      <PageHeader
        title={t("patients.title")}
        demo
        actions={
          !creating && (
            <button type="button" className="btn" onClick={() => setCreating(true)}>
              <Icon name="plus" size={18} />
              {t("patients.add")}
            </button>
          )
        }
      />

      {creating && (
        <PatientForm onCancel={() => setCreating(false)} onCreated={(p) => navigate(`/patients/${p.id}`)} />
      )}

      <div className="card toolbar">
        <div className="search">
          <Icon name="search" size={18} />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("patients.search.placeholder")}
            aria-label={t("patients.search.label")}
            autoComplete="off"
            maxLength={40}
          />
        </div>

        {hasConsentData && (
          <div className="chips" role="group" aria-label={t("patients.filter.label")}>
            {FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                className="chip"
                aria-pressed={activeFilter === f.value}
                onClick={() => setFilter(f.value)}
              >
                {t(f.key)}
              </button>
            ))}
          </div>
        )}

        {totalPages > 1 && query.trim() && <p className="muted small toolbar-note">{t("patients.search.pageNote")}</p>}
      </div>

      {failed && (
        <div className="alert" role="alert">
          {t("patients.error.load")}{" "}
          <button type="button" className="link-btn" onClick={() => void load(page)}>{t("common.retry")}</button>
        </div>
      )}

      {loading && !data && (
        <div className="patient-grid" aria-busy="true" aria-label={t("common.loading")}>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="patient-card skeleton" aria-hidden="true" />
          ))}
        </div>
      )}

      {data && items.length === 0 && !creating && (
        <div className="card empty">
          <p>{t("patients.empty")}</p>
          <button type="button" className="btn" onClick={() => setCreating(true)}>
            <Icon name="plus" size={18} />
            {t("patients.add")}
          </button>
        </div>
      )}

      {data && items.length > 0 && visible.length === 0 && (
        <div className="card empty"><p>{t("patients.noMatch")}</p></div>
      )}

      {visible.length > 0 && (
        <ul className="patient-grid" aria-label={t("patients.title")}>
          {visible.map((p) => {
            const details = meta(p);
            return (
              <li key={p.id}>
                <Link to={`/patients/${p.id}`} className="patient-card">
                  <span className="patient-card-head">
                    <span className="patient-code">{p.patient_code}</span>
                    {typeof p.consent_active === "boolean" &&
                      (p.consent_active ? (
                        <span className="pill pill-consent">
                          <Icon name="shield-check" size={14} />
                          {t("patients.consent.active")}
                        </span>
                      ) : (
                        <span className="pill pill-noconsent">
                          <Icon name="shield-off" size={14} />
                          {t("patients.consent.none")}
                        </span>
                      ))}
                  </span>
                  <span className="patient-meta">{details || t("patients.noDetails")}</span>
                  {typeof p.medication_count === "number" && (
                    <span className="patient-meta">
                      {t(p.medication_count === 1 ? "patients.medicines.one" : "patients.medicines", { n: p.medication_count })}
                    </span>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      )}

      {data && totalPages > 1 && (
        <nav className="pager" aria-label={t("patients.page")}>
          <button type="button" className="btn secondary" disabled={!data.previous || loading} onClick={() => setPage((p) => p - 1)}>
            {t("patients.prev")}
          </button>
          <span className="muted">{t("patients.page")} {page} / {totalPages}</span>
          <button type="button" className="btn secondary" disabled={!data.next || loading} onClick={() => setPage((p) => p + 1)}>
            {t("patients.next")}
          </button>
        </nav>
      )}
    </section>
  );
}