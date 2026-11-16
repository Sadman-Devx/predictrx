import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import "../../styles/results.css";
import { useI18n, type MessageKey } from "../../i18n";
import { pickSummary, SEVERITIES, severityCounts, sortFindings, verificationCounts, VERIFICATIONS } from "../../lib/results";
import type { AgentTraceStep, AnalysisRunStatus } from "../../lib/types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { StatusPill } from "../ui/StatusPill";
import { Tabs } from "../ui/Tabs";
import { FindingCard } from "./FindingCard";
import { PatientCardView } from "./PatientCardView";
import { TraceView } from "./TraceView";
import { TwinView } from "./TwinView";
import { VerificationBadge } from "./VerificationBadge";

interface Props {
  /** A run whose status is "completed": the server sends the findings, the summary and the frozen medicine list with it. */
  run: AnalysisRunStatus;
  trace: AgentTraceStep[];
  traceKnown: boolean;
}

const GAP_REASON: Record<string, MessageKey> = {
  needs_user_selection: "results.gap.needs_user_selection",
};

type TabId = "doctor" | "card" | "trace" | "twin";

function tabFrom(id: string): TabId {
  return id === "trace" || id === "card" || id === "twin" ? id : "doctor";
}

/**
 * Results screen (Day 7). Tabs: Doctor view · Patient card (Day 9) · Agent trace · What-if (Day 10, a labelled simulation
 * that starts from this completed analysis and never changes it).
 *
 * Doctor view order (design.md §1.4): overview + summary → anything NOT checked (gaps) → guardrail notice → findings
 * sorted by severity next to the medicines that were analysed. Nothing is hidden: "unknown", "unverified" and "conflict"
 * findings, medicines that could not be matched and guardrail changes are all shown.
 */
export function AnalysisResults({ run, trace, traceKnown }: Props) {
  const { t, lang } = useI18n();
  const [tab, setTab] = useState<TabId>("doctor");

  const findings = useMemo(() => sortFindings(run.findings ?? []), [run.findings]);
  const sev = useMemo(() => severityCounts(findings), [findings]);
  const ver = useMemo(() => verificationCounts(findings), [findings]);
  const summary = pickSummary(run.summary, lang);
  const medicines = run.medications ?? [];
  const gaps = run.gaps ?? [];
  const violations = run.guardrail_violations ?? [];
  // Generic names of the matched medicines: the What-if tab refuses to "add" one of these a second time.
  const baseGenerics = useMemo(
    () => (run.medications ?? []).map((m) => (m.generic_name ?? "").trim()).filter((g) => g !== ""),
    [run.medications],
  );

  if (run.findings == null) {
    return (
      <div className="card empty">
        <p role="alert">{t("results.unavailable")}</p>
      </div>
    );
  }

  const countText =
    findings.length === 0
      ? t("analysis.done.none") // never a "safe" statement
      : findings.length === 1
        ? t("analysis.done.one")
        : t("analysis.done.count", { n: findings.length });

  const doctor = (
    <>
      <div className="card overview">
        <div className="overview-head">
          {/* "complete" means the pipeline finished, not that the medicines are safe. */}
          <StatusPill tone="ok">{t("analysis.status.completed")}</StatusPill>
          <span className="muted small">
            {t(run.medication_count === 1 ? "patients.medicines.one" : "patients.medicines", { n: run.medication_count })}
          </span>
        </div>

        <p>{countText}</p>

        {findings.length > 0 && (
          <>
            <div className="count-row" role="group" aria-label={t("results.sev.label")}>
              {SEVERITIES.filter((s) => sev[s] > 0).map((s) => (
                <span key={s} className="count-item">
                  <SeverityBadge severity={s} />
                  <strong>{sev[s]}</strong>
                </span>
              ))}
            </div>
            <div className="count-row" role="group" aria-label={t("results.verify.label")}>
              {VERIFICATIONS.filter((v) => ver[v] > 0).map((v) => (
                <span key={v} className="count-item">
                  <VerificationBadge status={v} />
                  <strong>{ver[v]}</strong>
                </span>
              ))}
            </div>
          </>
        )}

        <div>
          <h2>{t("results.summary.title")}</h2>
          {summary ? (
            <>
              <p className="summary-text">{summary.text}</p>
              {summary.lang !== lang && (
                <p className="muted small">{t(summary.lang === "en" ? "results.summary.onlyEn" : "results.summary.onlyBn")}</p>
              )}
              <p className="muted small">{t("results.summary.note")}</p>
            </>
          ) : (
            <p className="muted">{t("results.summary.none")}</p>
          )}
        </div>

        <p className="muted small">{t("results.disclaimerVersion", { v: run.disclaimer_version })}</p>
      </div>

      {gaps.length > 0 && (
        <div className="card notice" role="note">
          <h2>{t("results.gaps.title")}</h2>
          <p>{t("results.gaps.hint")}</p>
          <ul>
            {gaps.map((g) => (
              <li key={g.medication_id}>
                <strong>{g.brand_name || g.raw_text}</strong> — {t(GAP_REASON[g.reason] ?? "results.gap.other")}
              </li>
            ))}
          </ul>
        </div>
      )}

      {violations.length > 0 && (
        <div className="card notice" role="note">
          <h2>{t("results.guardrail.title")}</h2>
          <p>{t("results.guardrail.hint", { n: violations.length })}</p>
          <details>
            <summary>{t("results.guardrail.details")}</summary>
            <ul>
              {violations.map((v, i) => (
                <li key={`${v}-${i}`}><code>{v}</code></li>
              ))}
            </ul>
          </details>
        </div>
      )}

      <div className="results-grid">
        <section aria-labelledby="findings-heading">
          <h2 id="findings-heading">{t("results.findings.title", { n: findings.length })}</h2>
          {findings.length === 0 ? (
            <div className="card"><p>{t("analysis.done.none")}</p></div>
          ) : (
            <ol className="finding-list">
              {findings.map((f) => (
                <FindingCard key={f.id} finding={f} />
              ))}
            </ol>
          )}
        </section>

        <aside className="results-side" aria-labelledby="medicines-heading">
          <div className="card">
            <h2 id="medicines-heading">{t("results.medicines.title")}</h2>
            {medicines.length === 0 ? (
              <p className="muted">{t("results.medicines.none")}</p>
            ) : (
              <ul className="med-summary">
                {medicines.map((m, i) => {
                  const entered = (m.brand_name || m.raw_text || "").trim();
                  const generic = m.generic_name ?? "";
                  const showEntered = entered !== "" && entered.toLowerCase() !== generic.toLowerCase();
                  return (
                    <li key={m.medication_id ?? `m-${i}`}>
                      <strong>{generic || entered || "—"}</strong>
                      {showEntered && (
                        <span className="muted small">
                          {t("results.medicines.asEntered")}: {entered}
                        </span>
                      )}
                      {m.strength && <span className="muted small">{m.strength}</span>}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="results-actions">
            <Link to={`/patients/${run.patient_id}`} className="btn secondary">{t("analysis.done.patient")}</Link>
            <Link to="/scan" className="btn">{t("dashboard.cta")}</Link>
          </div>
        </aside>
      </div>
    </>
  );

  return (
    <Tabs
      label={t("results.tabs.label")}
      active={tab}
      onChange={(id) => setTab(tabFrom(id))}
      tabs={[
        { id: "doctor", label: t("results.tab.doctor"), panel: doctor },
        { id: "card", label: t("results.tab.card"), panel: <PatientCardView runId={run.run_id} active={tab === "card"} /> },
        { id: "trace", label: t("results.tab.trace"), panel: <TraceView trace={trace} traceKnown={traceKnown} /> },
        {
          id: "twin",
          label: t("results.tab.twin"),
          panel: <TwinView runId={run.run_id} active={tab === "twin"} baseGenerics={baseGenerics} />,
        },
      ]}
    />
  );
}