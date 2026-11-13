import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { MedicationForm } from "../components/patient/MedicationForm";
import { Icon } from "../components/ui/Icon";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusPill, type Tone } from "../components/ui/StatusPill";
import { useI18n, type MessageKey } from "../i18n";
import { ApiRequestError } from "../lib/api";
import { getPatient, listMedications } from "../lib/clinical";
import type { Medication, Patient, ResolutionStatus } from "../lib/types";

const STATUS: Record<ResolutionStatus, { key: MessageKey; tone: Tone }> = {
  unresolved: { key: "meds.status.unresolved", tone: "stop" },
  resolved: { key: "meds.status.resolved", tone: "neutral" },
  user_confirmed: { key: "meds.status.user_confirmed", tone: "ok" },
};

const SEX_KEY: Record<string, MessageKey> = {
  male: "patients.sex.male",
  female: "patients.sex.female",
  other: "patients.sex.other",
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

  if (loading) return <p className="muted" role="status">{t("common.loading")}</p>;

  if (error || !patient) {
    return (
      <section>
        <p className="alert" role="alert">{t(error ?? "patients.notFound")}</p>
        <Link to="/patients" className="back-link"><Icon name="arrow-left" size={18} />{t("patients.back")}</Link>
      </section>
    );
  }

  const year = new Date().getFullYear();
  const w = patient.weight_kg !== null && patient.weight_kg !== "" ? Number(patient.weight_kg) : NaN;
  const facts = [
    patient.birth_year ? t("patients.age", { n: year - patient.birth_year }) : null,
    patient.sex && SEX_KEY[patient.sex] ? t(SEX_KEY[patient.sex]) : null,
    Number.isFinite(w) ? t("patients.kg", { n: w }) : null,
  ].filter((x): x is string => x !== null);

  return (
    <section>
      <Link to="/patients" className="back-link"><Icon name="arrow-left" size={18} />{t("patients.back")}</Link>

      <PageHeader title={patient.patient_code} subtitle={facts.length ? facts.join(" · ") : t("patients.noDetails")} demo />

      <div className="card">
        <h2>{t("meds.title")}</h2>

        {meds.length === 0 ? (
          <p className="muted">{t("meds.empty")}</p>
        ) : (
          <div className="table-wrap">
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
                    <td>
                      <StatusPill tone={STATUS[m.resolution_status].tone}>{t(STATUS[m.resolution_status].key)}</StatusPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <MedicationForm patientId={patient.id} onAdded={(m) => setMeds((prev) => [m, ...prev])} />
    </section>
  );
}