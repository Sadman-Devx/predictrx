import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../../i18n";
import { getAnalysis } from "../../lib/analysis";
import { formatWhen } from "../../lib/format";
import type {
  AnalysisRunStatus,
  PatientAnalysisHistoryRun,
  RiskFinding,
  SnapshotMedication,
} from "../../lib/types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { VerificationBadge } from "../analysis/VerificationBadge";

interface Props {
  patientId: number;
  previous: PatientAnalysisHistoryRun;
  latest: PatientAnalysisHistoryRun;
}

type MedicationChange =
  | { kind: "added"; before: null; after: SnapshotMedication }
  | { kind: "removed"; before: SnapshotMedication; after: null }
  | { kind: "updated"; before: SnapshotMedication; after: SnapshotMedication };

interface FindingChange {
  before: RiskFinding | null;
  after: RiskFinding | null;
}

interface Comparison {
  previous: AnalysisRunStatus & { medications: SnapshotMedication[]; findings: RiskFinding[] };
  latest: AnalysisRunStatus & { medications: SnapshotMedication[]; findings: RiskFinding[] };
}

function hasSnapshotData(
  run: AnalysisRunStatus,
  patientId: number,
): run is AnalysisRunStatus & { medications: SnapshotMedication[]; findings: RiskFinding[] } {
  return run.patient_id === patientId
    && run.status === "completed"
    && Array.isArray(run.medications)
    && Array.isArray(run.findings);
}

function normalize(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function medicationKey(medicine: SnapshotMedication): string {
  if (medicine.medication_id !== null) return `id:${medicine.medication_id}`;
  const name = normalize(medicine.generic_name) || normalize(medicine.brand_name) || normalize(medicine.raw_text);
  return `name:${name}|strength:${normalize(medicine.strength)}`;
}

function medicationSignature(medicine: SnapshotMedication): string {
  return JSON.stringify([
    normalize(medicine.raw_text),
    normalize(medicine.brand_name),
    normalize(medicine.generic_name),
    normalize(medicine.strength),
    normalize(medicine.resolution_status),
  ]);
}

function compareMedications(previous: SnapshotMedication[], latest: SnapshotMedication[]) {
  const before = new Map(previous.map((medicine) => [medicationKey(medicine), medicine]));
  const after = new Map(latest.map((medicine) => [medicationKey(medicine), medicine]));
  const added: Extract<MedicationChange, { kind: "added" }>[] = [];
  const removed: Extract<MedicationChange, { kind: "removed" }>[] = [];
  const updated: Extract<MedicationChange, { kind: "updated" }>[] = [];

  for (const [key, medicine] of after) {
    const oldMedicine = before.get(key);
    if (!oldMedicine) added.push({ kind: "added", before: null, after: medicine });
    else if (medicationSignature(oldMedicine) !== medicationSignature(medicine)) {
      updated.push({ kind: "updated", before: oldMedicine, after: medicine });
    }
  }
  for (const [key, medicine] of before) {
    if (!after.has(key)) removed.push({ kind: "removed", before: medicine, after: null });
  }

  return { added, removed, updated };
}

function findingKey(finding: RiskFinding): string {
  return [finding.drug_a.id, finding.drug_b.id].sort((a, b) => a - b).join(":");
}

function findingSignature(finding: RiskFinding): string {
  const evidence = (finding.evidence ?? [])
    .map((item) => JSON.stringify([
      item.type, item.id, item.source, item.label, item.section, item.excerpt, item.available,
    ]))
    .sort();
  return JSON.stringify([
    finding.severity,
    finding.verification_status,
    finding.rationale,
    finding.confidence,
    evidence,
  ]);
}

function compareFindings(previous: RiskFinding[], latest: RiskFinding[]) {
  const before = new Map(previous.map((finding) => [findingKey(finding), finding]));
  const after = new Map(latest.map((finding) => [findingKey(finding), finding]));
  const added: FindingChange[] = [];
  const absent: FindingChange[] = [];
  const changed: FindingChange[] = [];
  let unchanged = 0;

  for (const [key, current] of after) {
    const oldFinding = before.get(key);
    if (!oldFinding) added.push({ before: null, after: current });
    else if (findingSignature(oldFinding) !== findingSignature(current)) {
      changed.push({ before: oldFinding, after: current });
    } else {
      unchanged += 1;
    }
  }
  for (const [key, oldFinding] of before) {
    if (!after.has(key)) absent.push({ before: oldFinding, after: null });
  }

  return { added, absent, changed, unchanged };
}

function medicineLabel(medicine: SnapshotMedication, fallback: string): string {
  const name = medicine.generic_name?.trim() || medicine.brand_name.trim() || medicine.raw_text.trim() || fallback;
  return medicine.strength.trim() ? `${name} · ${medicine.strength.trim()}` : name;
}

function SnapshotCard({
  label,
  runId,
  occurredAt,
  lang,
  unknownDate,
  openAnalysis,
}: {
  label: string;
  runId: number;
  occurredAt: string | null;
  lang: "bn" | "en";
  unknownDate: string;
  openAnalysis: string;
}) {
  return (
    <div className="therapy-evolution-snapshot">
      <span>{label}</span>
      <time dateTime={occurredAt ?? undefined}>{formatWhen(occurredAt, lang) || unknownDate}</time>
      <Link to={`/analysis/${runId}`}>{openAnalysis}</Link>
    </div>
  );
}

function MedicationChangeGroup({
  title,
  changes,
  unknownMedicine,
}: {
  title: string;
  changes: MedicationChange[];
  unknownMedicine: string;
}) {
  return (
    <section className="therapy-evolution-group">
      <h4>{title}<span>{changes.length}</span></h4>
      {changes.length === 0 ? (
        <p className="muted small">—</p>
      ) : (
        <ul>
          {changes.map((change, index) => {
            const identity = change.kind === "removed" ? change.before : change.after;
            return (
              <li key={`${change.kind}-${medicationKey(identity)}-${index}`}>
                {change.kind === "updated" ? (
                  <>
                    <span>{medicineLabel(change.before, unknownMedicine)}</span>
                    <span className="therapy-evolution-arrow" aria-hidden="true">→</span>
                    <strong>{medicineLabel(change.after, unknownMedicine)}</strong>
                  </>
                ) : (
                  <strong>{medicineLabel(change.kind === "added" ? change.after : change.before, unknownMedicine)}</strong>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function FindingState({ label, finding }: { label: string; finding: RiskFinding }) {
  return (
    <div className="therapy-evolution-finding-state">
      <span>{label}</span>
      <SeverityBadge severity={finding.severity} />
      <VerificationBadge status={finding.verification_status} />
    </div>
  );
}

function FindingChangeGroup({
  title,
  changes,
  kind,
  previousRunId,
  latestRunId,
  previousLabel,
  latestLabel,
  openAnalysis,
  count,
}: {
  title: string;
  changes: FindingChange[];
  kind: "added" | "absent" | "changed";
  previousRunId: number;
  latestRunId: number;
  previousLabel: string;
  latestLabel: string;
  openAnalysis: string;
  count: string;
}) {
  if (changes.length === 0) return null;

  return (
    <details className="therapy-evolution-finding-group">
      <summary>{title}<span>{count}</span></summary>
      <ul>
        {changes.map((change) => {
          const finding = change.after ?? change.before;
          if (!finding) return null;
          const runId = kind === "absent" ? previousRunId : latestRunId;
          return (
            <li key={`${kind}-${findingKey(finding)}`}>
              <div className="therapy-evolution-finding-heading">
                <strong>{finding.drug_a.generic_name} + {finding.drug_b.generic_name}</strong>
                <Link to={`/analysis/${runId}`}>{openAnalysis}</Link>
              </div>
              <div className="therapy-evolution-finding-states">
                {change.before && <FindingState label={previousLabel} finding={change.before} />}
                {change.after && <FindingState label={latestLabel} finding={change.after} />}
              </div>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

export function TherapyEvolution({ patientId, previous, latest }: Props) {
  const { lang, t } = useI18n();
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const number = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    setComparison(null);

    Promise.all([
      getAnalysis(previous.run_id, controller.signal),
      getAnalysis(latest.run_id, controller.signal),
    ])
      .then(([before, after]) => {
        if (!active) return;
        if (!hasSnapshotData(before, patientId) || !hasSnapshotData(after, patientId)) {
          setError(true);
          return;
        }
        setComparison({ previous: before, latest: after });
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [patientId, previous.run_id, latest.run_id, retry]);

  const medicationChanges = comparison
    ? compareMedications(comparison.previous.medications, comparison.latest.medications)
    : null;
  const findingChanges = comparison
    ? compareFindings(comparison.previous.findings, comparison.latest.findings)
    : null;
  const noChanges = medicationChanges && findingChanges
    ? medicationChanges.added.length + medicationChanges.removed.length + medicationChanges.updated.length
        + findingChanges.added.length + findingChanges.absent.length + findingChanges.changed.length === 0
    : false;

  return (
    <section className="therapy-evolution" aria-labelledby="therapy-evolution-title" aria-busy={loading}>
      <header className="therapy-evolution-header">
        <div>
          <p className="patient-history-eyebrow">{t("patients.evolution.eyebrow")}</p>
          <h3 id="therapy-evolution-title">{t("patients.evolution.title")}</h3>
        </div>
        <span className="therapy-evolution-mark" aria-hidden="true">↗</span>
      </header>
      <p className="therapy-evolution-note">{t("patients.evolution.note")}</p>

      {loading ? (
        <p className="muted" role="status">{t("common.loading")}</p>
      ) : error || !comparison || !medicationChanges || !findingChanges ? (
        <div className="patient-history-error" role="alert">
          <span>{t("patients.evolution.error")}</span>
          <button type="button" className="btn btn-small" onClick={() => setRetry((value) => value + 1)}>
            {t("common.retry")}
          </button>
        </div>
      ) : (
        <>
          <div className="therapy-evolution-snapshots">
            <SnapshotCard
              label={t("patients.evolution.previous")}
              runId={previous.run_id}
              occurredAt={previous.occurred_at}
              lang={lang}
              unknownDate={t("patients.evolution.unknownDate")}
              openAnalysis={t("patients.evolution.openAnalysis")}
            />
            <span className="therapy-evolution-connector" aria-hidden="true">→</span>
            <SnapshotCard
              label={t("patients.evolution.latest")}
              runId={latest.run_id}
              occurredAt={latest.occurred_at}
              lang={lang}
              unknownDate={t("patients.evolution.unknownDate")}
              openAnalysis={t("patients.evolution.openAnalysis")}
            />
          </div>

          <div className="therapy-evolution-metrics" aria-label={t("patients.evolution.findingSummary")}>
            <Metric label={t("patients.evolution.newFindings")} value={findingChanges.added.length} number={number} />
            <Metric label={t("patients.evolution.absentFindings")} value={findingChanges.absent.length} number={number} />
            <Metric label={t("patients.evolution.changedFindings")} value={findingChanges.changed.length} number={number} />
            <Metric label={t("patients.evolution.unchangedFindings")} value={findingChanges.unchanged} number={number} />
          </div>

          {noChanges && <p className="therapy-evolution-no-changes">{t("patients.evolution.noChanges")}</p>}

          <section className="therapy-evolution-section">
            <h4>{t("patients.evolution.medicineChanges")}</h4>
            <div className="therapy-evolution-delta-grid">
              <MedicationChangeGroup
                title={t("patients.evolution.medicinesAdded")}
                changes={medicationChanges.added}
                unknownMedicine={t("patients.evolution.unknownMedicine")}
              />
              <MedicationChangeGroup
                title={t("patients.evolution.medicinesRemoved")}
                changes={medicationChanges.removed}
                unknownMedicine={t("patients.evolution.unknownMedicine")}
              />
              <MedicationChangeGroup
                title={t("patients.evolution.medicinesUpdated")}
                changes={medicationChanges.updated}
                unknownMedicine={t("patients.evolution.unknownMedicine")}
              />
            </div>
          </section>

          <section className="therapy-evolution-section">
            <h4>{t("patients.evolution.findingChanges")}</h4>
            <div className="therapy-evolution-finding-summary">
              <FindingChangeGroup
                title={t("patients.evolution.newFindings")}
                changes={findingChanges.added}
                kind="added"
                previousRunId={previous.run_id}
                latestRunId={latest.run_id}
                previousLabel={t("patients.evolution.previous")}
                latestLabel={t("patients.evolution.latest")}
                openAnalysis={t("patients.evolution.openAnalysis")}
                count={number.format(findingChanges.added.length)}
              />
              <FindingChangeGroup
                title={t("patients.evolution.absentFindings")}
                changes={findingChanges.absent}
                kind="absent"
                previousRunId={previous.run_id}
                latestRunId={latest.run_id}
                previousLabel={t("patients.evolution.previous")}
                latestLabel={t("patients.evolution.latest")}
                openAnalysis={t("patients.evolution.openAnalysis")}
                count={number.format(findingChanges.absent.length)}
              />
              <FindingChangeGroup
                title={t("patients.evolution.changedFindings")}
                changes={findingChanges.changed}
                kind="changed"
                previousRunId={previous.run_id}
                latestRunId={latest.run_id}
                previousLabel={t("patients.evolution.previous")}
                latestLabel={t("patients.evolution.latest")}
                openAnalysis={t("patients.evolution.openAnalysis")}
                count={number.format(findingChanges.changed.length)}
              />
            </div>
          </section>
        </>
      )}
    </section>
  );
}

function Metric({ label, value, number }: { label: string; value: number; number: Intl.NumberFormat }) {
  return (
    <div className="therapy-evolution-metric">
      <strong>{number.format(value)}</strong>
      <span>{label}</span>
    </div>
  );
}
