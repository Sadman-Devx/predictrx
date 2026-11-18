import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { useI18n, type MessageKey } from "../i18n";
import { listPatientAnalyses } from "../lib/analysis";
import { listPatientOptions } from "../lib/clinical";
import { createFollowUp, listFollowUps, updateFollowUp } from "../lib/followups";
import { formatWhen } from "../lib/format";
import type {
  AnalysisListItem,
  FollowUpTask,
  FollowUpTaskCreate,
  FollowUpTaskStatus,
  FollowUpTaskType,
  Paginated,
  Patient,
} from "../lib/types";
import "../styles/followups.css";

const STATUSES: FollowUpTaskStatus[] = ["to_review", "in_progress", "done"];
const STATUS_LABELS: Record<FollowUpTaskStatus, MessageKey> = {
  to_review: "followups.status.toReview",
  in_progress: "followups.status.inProgress",
  done: "followups.status.done",
};
const EMPTY_LABELS: Record<FollowUpTaskStatus, MessageKey> = {
  to_review: "followups.empty.to_review",
  in_progress: "followups.empty.in_progress",
  done: "followups.empty.done",
};
const TASK_TYPES: FollowUpTaskType[] = [
  "review_analysis",
  "patient_contact",
  "medication_reconciliation",
  "follow_up_visit",
];
const TASK_TYPE_LABELS: Record<FollowUpTaskType, MessageKey> = {
  review_analysis: "followups.type.reviewAnalysis",
  patient_contact: "followups.type.patientContact",
  medication_reconciliation: "followups.type.medicationReconciliation",
  follow_up_visit: "followups.type.followUpVisit",
};

function localDate(): string {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export default function FollowUps() {
  const { t, lang } = useI18n();
  const [tasks, setTasks] = useState<FollowUpTask[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisListItem[]>([]);
  const [patientId, setPatientId] = useState("");
  const [analysisRunId, setAnalysisRunId] = useState("");
  const [taskType, setTaskType] = useState<FollowUpTaskType>("review_analysis");
  const [dueDate, setDueDate] = useState("");
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [taskCount, setTaskCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingIds, setSavingIds] = useState<Set<number>>(() => new Set());
  const [failed, setFailed] = useState(false);
  const [patientLoadFailed, setPatientLoadFailed] = useState(false);
  const [analysisLoadFailed, setAnalysisLoadFailed] = useState(false);
  const [actionError, setActionError] = useState<MessageKey | null>(null);

  const loadTasks = useCallback(async (page = 1, append = false) => {
    setLoading(true);
    setFailed(false);
    try {
      const data: Paginated<FollowUpTask> = await listFollowUps(page);
      setTasks((current) => append ? [...current, ...data.results] : data.results);
      setTaskCount(data.count);
      setNextPage(data.next ? page + 1 : null);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    let active = true;
    listPatientOptions()
      .then((result) => { if (active) setPatients(result); })
      .catch(() => { if (active) setPatientLoadFailed(true); })
      .finally(() => { if (active) setLoadingPatients(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!patientId) {
      setAnalyses([]);
      setAnalysisRunId("");
      setAnalysisLoadFailed(false);
      return;
    }
    let active = true;
    setAnalyses([]);
    setAnalysisRunId("");
    setAnalysisLoadFailed(false);
    listPatientAnalyses(Number(patientId))
      .then((data) => { if (active) setAnalyses(data.results); })
      .catch(() => { if (active) setAnalysisLoadFailed(true); });
    return () => { active = false; };
  }, [patientId]);

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!patientId) return;
    setSaving(true);
    setActionError(null);
    const data: FollowUpTaskCreate = {
      patient_id: Number(patientId),
      analysis_run_id: analysisRunId ? Number(analysisRunId) : null,
      task_type: taskType,
      due_date: dueDate || null,
    };
    try {
      const created = await createFollowUp(data);
      setTasks((current) => [created, ...current]);
      setTaskCount((count) => count + 1);
      setTaskType("review_analysis");
      setDueDate("");
    } catch {
      setActionError("followups.error.create");
    } finally {
      setSaving(false);
    }
  }

  async function saveTask(task: FollowUpTask, changes: { status?: FollowUpTaskStatus; due_date?: string | null }) {
    setSavingIds((current) => new Set(current).add(task.id));
    setActionError(null);
    try {
      const updated = await updateFollowUp(task.id, changes);
      setTasks((current) => current.map((item) => item.id === task.id ? updated : item));
    } catch {
      setActionError("followups.error.update");
    } finally {
      setSavingIds((current) => {
        const next = new Set(current);
        next.delete(task.id);
        return next;
      });
    }
  }

  const today = localDate();

  return (
    <section className="followups-page">
      <PageHeader title={t("followups.title")} subtitle={t("followups.subtitle")} />

      <div className="card followups-create">
        <div className="followups-section-heading">
          <div>
            <h2>{t("followups.create.title")}</h2>
            <p className="muted">{t("followups.create.hint")}</p>
          </div>
          <span className="followups-count">{t("followups.total", { n: taskCount })}</span>
        </div>
        <form className="followups-form" onSubmit={(event) => void onCreate(event)}>
          <label className="field">
            {t("followups.patient")}
            <select value={patientId} onChange={(event) => setPatientId(event.target.value)} required disabled={loadingPatients}>
              <option value="">{t("followups.patient.placeholder")}</option>
              {patients.map((patient) => (
                <option key={patient.id} value={patient.id}>{patient.patient_code}</option>
              ))}
            </select>
          </label>
          <label className="field">
            {t("followups.taskType")}
            <select value={taskType} onChange={(event) => setTaskType(event.target.value as FollowUpTaskType)}>
              {TASK_TYPES.map((type) => <option key={type} value={type}>{t(TASK_TYPE_LABELS[type])}</option>)}
            </select>
          </label>
          <label className="field">
            {t("followups.analysis")}
            <select
              value={analysisRunId}
              onChange={(event) => setAnalysisRunId(event.target.value)}
              disabled={!patientId || analysisLoadFailed}
            >
              <option value="">{t("followups.analysis.none")}</option>
              {analyses.map((analysis) => (
                <AnalysisOption key={analysis.run_id} analysis={analysis} lang={lang} label={t("followups.run", { id: analysis.run_id })} />
              ))}
            </select>
          </label>
          <label className="field">
            {t("followups.dueDate")}
            <input type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
          </label>
          <button type="submit" className="btn followups-submit" disabled={saving || loadingPatients || !patientId}>
            {saving ? t("followups.creating") : t("followups.create.submit")}
          </button>
        </form>
        {(patientLoadFailed || analysisLoadFailed) && (
          <p className="followups-inline-error" role="alert">
            {t(patientLoadFailed ? "followups.error.patients" : "followups.error.analyses")}
          </p>
        )}
      </div>

      {actionError && <p className="alert" role="alert">{t(actionError)}</p>}
      {failed && (
        <p className="alert" role="alert">
          {t("followups.error.load")}{" "}
          <button type="button" className="link-btn" onClick={() => void loadTasks()}>{t("common.retry")}</button>
        </p>
      )}
      {loading && tasks.length === 0 && <p className="muted" role="status">{t("common.loading")}</p>}

      <div className="followups-board" aria-busy={loading}>
        {STATUSES.map((status) => {
          const columnTasks = tasks.filter((task) => task.status === status);
          return (
            <section className={`followups-column followups-column-${status}`} key={status} aria-labelledby={`followups-${status}`}>
              <header className="followups-column-header">
                <h2 id={`followups-${status}`}>{t(STATUS_LABELS[status])}</h2>
                <span>{columnTasks.length}</span>
              </header>
              {columnTasks.length === 0 ? (
                <p className="followups-column-empty">{t(EMPTY_LABELS[status])}</p>
              ) : (
                <ul className="followups-card-list">
                  {columnTasks.map((task) => {
                    const overdue = status !== "done" && !!task.due_date && task.due_date < today;
                    return (
                      <li key={task.id}>
                        <article className={`followups-task${overdue ? " is-overdue" : ""}`}>
                          <div className="followups-task-top">
                            <span className="followups-type">{t(TASK_TYPE_LABELS[task.task_type])}</span>
                            {overdue && <span className="followups-overdue">{t("followups.overdue")}</span>}
                          </div>
                          <Link to={`/patients/${task.patient_id}`} className="followups-patient">{task.patient_code}</Link>
                          {task.analysis_run_id && (
                            <Link to={`/analysis/${task.analysis_run_id}`} className="followups-analysis">
                              {t("followups.run", { id: task.analysis_run_id })}
                            </Link>
                          )}
                          <label className="followups-status-control">
                            <span>{t("followups.status.label")}</span>
                            <select
                              value={task.status}
                              disabled={savingIds.has(task.id)}
                              onChange={(event) => void saveTask(task, { status: event.target.value as FollowUpTaskStatus })}
                            >
                              {STATUSES.map((value) => <option key={value} value={value}>{t(STATUS_LABELS[value])}</option>)}
                            </select>
                          </label>
                          <label className="followups-date-control">
                            <span>{t("followups.dueDate")}</span>
                            <input
                              key={`${task.id}-${task.due_date ?? ""}`}
                              type="date"
                              defaultValue={task.due_date ?? ""}
                              aria-label={t("followups.dueDateFor", { patient: task.patient_code })}
                              disabled={savingIds.has(task.id)}
                              onBlur={(event) => {
                                const nextDate = event.currentTarget.value || null;
                                if (nextDate !== task.due_date) void saveTask(task, { due_date: nextDate });
                              }}
                            />
                          </label>
                        </article>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          );
        })}
      </div>

      {nextPage && (
        <button type="button" className="btn secondary followups-more" disabled={loading}
          onClick={() => void loadTasks(nextPage, true)}>
          {t("followups.loadMore")}
        </button>
      )}
    </section>
  );
}

function AnalysisOption({ analysis, lang, label }: { analysis: AnalysisListItem; lang: "bn" | "en"; label: string }) {
  const date = formatWhen(analysis.finished_at ?? analysis.started_at, lang);
  return <option value={analysis.run_id}>{date ? `${label} · ${date}` : label}</option>;
}
