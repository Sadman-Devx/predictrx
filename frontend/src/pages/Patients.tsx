import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PatientForm } from "../components/patient/PatientForm";
import { useI18n, type MessageKey } from "../i18n";
import { listPatients } from "../lib/clinical";
import type { Paginated, Patient } from "../lib/types";

const SEX_KEY: Record<string, MessageKey> = {
  male: "patients.sex.male",
  female: "patients.sex.female",
  other: "patients.sex.other",
};

export default function Patients() {
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Paginated<Patient> | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [creating, setCreating] = useState(false);

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

  const dateFmt = new Intl.DateTimeFormat(lang === "bn" ? "bn-BD" : "en-GB", { dateStyle: "medium" });
  const totalPages = data ? Math.max(1, Math.ceil(data.count / 20)) : 1; // backend PAGE_SIZE = 20

  return (
    <section>
      <div className="page-head">
        <h1>{t("patients.title")}</h1>
        {!creating && (
          <button type="button" className="btn" onClick={() => setCreating(true)}>
            {t("patients.add")}
          </button>
        )}
      </div>

      {creating && (
        <PatientForm
          onCancel={() => setCreating(false)}
          onCreated={(p) => navigate(`/patients/${p.id}`)}
        />
      )}

      {failed && (
        <div className="alert" role="alert">
          {t("patients.error.load")}{" "}
          <button type="button" className="link-btn" onClick={() => void load(page)}>{t("common.retry")}</button>
        </div>
      )}

      {loading && !data && <p className="muted">{t("common.loading")}</p>}

      {data && data.results.length === 0 && !creating && (
        <div className="card"><p>{t("patients.empty")}</p></div>
      )}

      {data && data.results.length > 0 && (
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("patients.code")}</th>
                <th scope="col">{t("patients.birthYear")}</th>
                <th scope="col">{t("patients.sex")}</th>
                <th scope="col">{t("patients.weight")}</th>
                <th scope="col">{t("patients.created")}</th>
                <th scope="col"><span className="sr-only">{t("patients.open")}</span></th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((p) => (
                <tr key={p.id}>
                  <th scope="row"><Link to={`/patients/${p.id}`}>{p.patient_code}</Link></th>
                  <td>{p.birth_year ?? "—"}</td>
                  <td>{p.sex && SEX_KEY[p.sex] ? t(SEX_KEY[p.sex]) : "—"}</td>
                  <td>{p.weight_kg ?? "—"}</td>
                  <td>{dateFmt.format(new Date(p.created_at))}</td>
                  <td><Link to={`/patients/${p.id}`}>{t("patients.open")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>

          {totalPages > 1 && (
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
        </div>
      )}
    </section>
  );
}