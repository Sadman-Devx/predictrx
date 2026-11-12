import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { MedicationForm } from "../components/patient/MedicationForm";
import { useI18n, type MessageKey } from "../i18n";
import { ApiRequestError } from "../lib/api";
import { getPatient, listMedications } from "../lib/clinical";
import type { Medication, Patient, ResolutionStatus } from "../lib/types";

const STATUS_KEY: Record<ResolutionStatus, MessageKey> = {
  unresolved: "meds.status.unresolved",
  resolved: "meds.status.resolved",
  user_confirmed: "meds.status.user_confirmed",
};

export default function PatientDetail() {
  const { t } = useI18n();
  const { id } = useParams();
  const patientId = Number(id);

  const [patient, setPatient] = useState<Patient | null>(null);
  const [meds, setMeds] = useState<Medication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<MessageKey | null>(null);

  const load = useCallback(async () => {
    if (!Number.isInteger(patientId)) {
      setError("patients.notFound");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [p, m] = await Promise.all([getPatient(patientId), listMedications(patientId)]);
      setPatient(p);
      setMeds(m);
    } catch (err) {
      setError(err instanceof ApiRequestError && err.status === 404 ? "patients.notFound" : "meds.error.load");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <p className="muted">{t("common.loading")}</p>;

  if (error || !patient) {
    return (
      <section>
        <p className="alert" role="alert">{t(error ?? "patients.notFound")}</p>
        <Link to="/patients">{t("patients.back")}</Link>
      </section>
    );
  }

  return (
    <section>
      <p><Link to="/patients">← {t("patients.back")}</Link></p>
      <h1>{patient.patient_code}</h1>
      <p className="muted">
        {t("patients.birthYear")}: {patient.birth_year ?? "—"} · {t("patients.weight")}: {patient.weight_kg ?? "—"}
      </p>

      <h2>{t("meds.title")}</h2>

      {meds.length === 0 ? (
        <div className="card"><p>{t("meds.empty")}</p></div>
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("meds.col.name")}</th>
                <th scope="col">{t("meds.col.generic")}</th>
                <th scope="col">{t("meds.col.strength")}</th>
                <th scope="col">{t("meds.col.frequency")}</th>
                <th scope="col">{t("meds.col.status")}</th>
              </tr>
            </thead>
            <tbody>
              {meds.map((m) => (
                <tr key={m.id}>
                  <th scope="row">{m.raw_text}</th>
                  <td>{m.generic_name ?? "—"}</td>
                  <td>{m.strength || "—"}</td>
                  <td>{m.frequency || "—"}</td>
                  <td><span className="badge">{t(STATUS_KEY[m.resolution_status])}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <MedicationForm patientId={patient.id} onAdded={(m) => setMeds((prev) => [m, ...prev])} />
    </section>
  );
}