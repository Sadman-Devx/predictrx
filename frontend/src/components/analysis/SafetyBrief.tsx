import { createPortal } from "react-dom";
import "../../styles/safety-brief.css";
import { useI18n, type MessageKey } from "../../i18n";
import { formatWhen } from "../../lib/format";
import {
  evidenceLink,
  evidenceMeta,
  evidenceSourceName,
  normalizeVerification,
  pickSummary,
  severityCounts,
  sortFindings,
  verificationCounts,
} from "../../lib/results";
import type { AnalysisRunStatus, RiskFinding, VerificationStatus } from "../../lib/types";

const VERIFICATION_LABEL: Record<VerificationStatus, MessageKey> = {
  verified: "verify.verified",
  unverified: "verify.unverified",
  conflict: "verify.conflict",
};

interface Props {
  run: AnalysisRunStatus;
  findings: RiskFinding[];
}

export function SafetyBrief({ run, findings }: Props) {
  const { t, lang } = useI18n();
  const medicines = run.medications ?? [];
  const gaps = run.gaps ?? [];
  const guardrailViolations = run.guardrail_violations ?? [];
  const sortedFindings = sortFindings(findings);
  const severity = severityCounts(sortedFindings);
  const verification = verificationCounts(sortedFindings);
  const summary = pickSummary(run.summary, lang);
  const number = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB");
  const completedAt = run.finished_at ? formatWhen(run.finished_at, lang) : "";
  const disclaimer = run.disclaimer
    ? lang === "bn" ? run.disclaimer.text_bn : run.disclaimer.text_en
    : "";
  const reviewCount = verification.unverified + verification.conflict;

  function printBrief() {
    const cleanup = () => document.body.classList.remove("printing-safety-brief");
    document.body.classList.add("printing-safety-brief");
    window.addEventListener("afterprint", cleanup, { once: true });
    window.print();
  }

  const report = (
    <article className="safety-brief-sheet" lang={lang} aria-label={t("safetyBrief.title")}>
      <header className="safety-brief-report-head">
        <div className="safety-brief-brand">Predict<span>Rx</span></div>
        <p className="safety-brief-eyebrow">{t("safetyBrief.eyebrow")}</p>
        <h1>{t("safetyBrief.title")}</h1>
        <p className="safety-brief-meta">
          {t("safetyBrief.analysisRef", { id: number.format(run.run_id) })}
          {completedAt && <> · {t("safetyBrief.completed", { date: completedAt })}</>}
        </p>
      </header>

      <div className="safety-brief-stats">
        <BriefStat label={t("safetyBrief.medicines")} value={number.format(medicines.length)} />
        <BriefStat label={t("safetyBrief.findings")} value={number.format(sortedFindings.length)} />
        <BriefStat label={t("severity.major")} value={number.format(severity.major)} tone="major" />
        <BriefStat label={t("severity.unknown")} value={number.format(severity.unknown)} tone="unknown" />
      </div>

      <section className="safety-brief-section">
        <h2>{t("results.summary.title")}</h2>
        {summary ? (
          <>
            <p className="safety-brief-summary">{summary.text}</p>
            {summary.lang !== lang && (
              <p className="safety-brief-muted">{t(summary.lang === "en" ? "results.summary.onlyEn" : "results.summary.onlyBn")}</p>
            )}
          </>
        ) : (
          <p className="safety-brief-muted">{t("results.summary.none")}</p>
        )}
      </section>

      <section className="safety-brief-section">
        <h2>{t("results.medicines.title")}</h2>
        {medicines.length === 0 ? (
          <p className="safety-brief-muted">{t("results.medicines.none")}</p>
        ) : (
          <ul className="safety-brief-medicines">
            {medicines.map((medicine, index) => {
              const entered = (medicine.brand_name || medicine.raw_text || "").trim();
              const generic = (medicine.generic_name ?? "").trim();
              return (
                <li key={medicine.medication_id ?? `medicine-${index}`}>
                  <strong>{generic || entered || "—"}</strong>
                  {entered && entered.toLowerCase() !== generic.toLowerCase() && (
                    <span>{t("results.medicines.asEntered")}: {entered}</span>
                  )}
                  {medicine.strength && <span>{medicine.strength}</span>}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="safety-brief-section">
        <div className="safety-brief-section-head">
          <h2>{t("results.findings.title", { n: sortedFindings.length })}</h2>
          <p className="safety-brief-muted">
            {t("safetyBrief.verificationSummary", {
              verified: number.format(verification.verified),
              unverified: number.format(reviewCount),
            })}
          </p>
        </div>
        {sortedFindings.length === 0 ? (
          <p className="safety-brief-muted">{t("analysis.done.none")}</p>
        ) : (
          <ol className="safety-brief-findings">
            {sortedFindings.map((finding) => {
              const status = normalizeVerification(finding.verification_status);
              return (
                <li key={finding.id} className={`safety-brief-finding severity-${finding.severity}`}>
                  <div className="safety-brief-finding-head">
                    <h3>{finding.drug_a.generic_name} + {finding.drug_b.generic_name}</h3>
                    <span className={`safety-brief-badge severity-${finding.severity}`}>
                      {t(`severity.${finding.severity}`)}
                    </span>
                    <span className={`safety-brief-badge verification-${status}`}>
                      {t(VERIFICATION_LABEL[status])}
                    </span>
                  </div>
                  {finding.rationale && <p>{finding.rationale}</p>}
                  {finding.evidence.length > 0 ? (
                    <ul className="safety-brief-sources">
                      {finding.evidence.map((item, index) => {
                        const link = evidenceLink(item);
                        const meta = evidenceMeta(item) || item.source_ref;
                        return (
                          <li key={`${item.type}-${item.id ?? "source"}-${index}`}>
                            <span>
                              {link ? (
                                <a href={link} target="_blank" rel="noreferrer noopener">{evidenceSourceName(item)}</a>
                              ) : evidenceSourceName(item)}
                              {item.id !== null && item.id !== undefined ? ` #${item.id}` : ""}
                            </span>
                            {meta && <span className="safety-brief-muted">{meta}</span>}
                            {!item.available && <span className="safety-brief-muted">{t("evidence.missing.short")}</span>}
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="safety-brief-muted">
                      {finding.severity === "unknown" ? t("finding.unknown.note") : t("finding.noSource")}
                    </p>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </section>

      {gaps.length > 0 && (
        <section className="safety-brief-section safety-brief-notice">
          <h2>{t("results.gaps.title")}</h2>
          <p>{t("safetyBrief.notChecked")}</p>
          <ul>
            {gaps.map((gap) => <li key={gap.medication_id}>{gap.brand_name || gap.raw_text}</li>)}
          </ul>
        </section>
      )}

      {guardrailViolations.length > 0 && (
        <p className="safety-brief-notice">
          {t("results.guardrail.hint", { n: guardrailViolations.length })}
        </p>
      )}

      <footer className="safety-brief-footer">
        <p>{disclaimer || t("disclaimer")}</p>
        <span>{t("results.disclaimerVersion", { v: run.disclaimer_version })}</span>
      </footer>
    </article>
  );

  return (
    <>
      <section className="card safety-brief-launch" aria-labelledby="safety-brief-title">
        <div className="safety-brief-launch-copy">
          <p className="safety-brief-eyebrow">{t("safetyBrief.eyebrow")}</p>
          <h2 id="safety-brief-title">{t("safetyBrief.title")}</h2>
          <p className="muted small">{t("safetyBrief.description")}</p>
          <div className="safety-brief-preview-stats" aria-label={t("safetyBrief.previewLabel")}>
            <BriefStat label={t("safetyBrief.medicines")} value={number.format(medicines.length)} />
            <BriefStat label={t("safetyBrief.findings")} value={number.format(sortedFindings.length)} />
            <BriefStat label={t("severity.major")} value={number.format(severity.major)} tone="major" />
            <BriefStat label={t("safetyBrief.needsReview")} value={number.format(reviewCount)} tone="review" />
          </div>
        </div>
        <button type="button" className="btn safety-brief-print-button" onClick={printBrief}>
          {t("safetyBrief.print")}
        </button>
      </section>
      {createPortal(report, document.body)}
    </>
  );
}

function BriefStat({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`safety-brief-stat${tone ? ` tone-${tone}` : ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
