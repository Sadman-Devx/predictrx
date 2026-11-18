import { useState } from "react";
import { useI18n, type MessageKey } from "../../i18n";
import { normalizeVerification } from "../../lib/results";
import type { RiskFinding } from "../../lib/types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { VerificationBadge } from "./VerificationBadge";

interface Props {
  findings: RiskFinding[];
}

function promptFor(finding: RiskFinding): MessageKey {
  if (finding.severity === "unknown") return "clinicalReview.prompt.unknown";

  const verification = normalizeVerification(finding.verification_status);
  if (verification === "conflict") return "clinicalReview.prompt.conflict";
  if (verification === "unverified") return "clinicalReview.prompt.unverified";
  return "clinicalReview.prompt.applicability";
}

export function ClinicalReviewChecklist({ findings }: Props) {
  const { t, lang } = useI18n();
  const [reviewedIds, setReviewedIds] = useState<Set<number>>(() => new Set());
  const number = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB");

  if (findings.length === 0) return null;

  const reviewedCount = findings.filter((finding) => reviewedIds.has(finding.id)).length;
  const progress = reviewedCount / findings.length;
  const circumference = 2 * Math.PI * 18;

  function toggleReviewed(id: number) {
    setReviewedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <section className="card clinical-review" aria-labelledby="clinical-review-title">
      <header className="clinical-review-header">
        <span className="clinical-review-mark" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M5 3.5h10a1.5 1.5 0 0 1 1.5 1.5v13H3.5V5A1.5 1.5 0 0 1 5 3.5Z" stroke="currentColor" strokeWidth="1.5" />
            <path d="M7 8h6M7 11h6M7 14h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </span>
        <div className="clinical-review-copy">
          <p className="clinical-review-eyebrow">{t("clinicalReview.eyebrow")}</p>
          <h2 id="clinical-review-title">{t("clinicalReview.title")}</h2>
          <p className="muted small">{t("clinicalReview.description")}</p>
        </div>
        <div className="clinical-review-progress-wrap">
          <div
            className="clinical-review-progress"
            role="img"
            aria-label={t("clinicalReview.progressLabel", {
              reviewed: number.format(reviewedCount),
              total: number.format(findings.length),
            })}
          >
            <svg viewBox="0 0 48 48" aria-hidden="true">
              <circle className="clinical-review-progress-track" cx="24" cy="24" r="18" />
              <circle
                className="clinical-review-progress-value"
                cx="24"
                cy="24"
                r="18"
                strokeDasharray={circumference}
                strokeDashoffset={circumference * (1 - progress)}
              />
            </svg>
            <span>{number.format(reviewedCount)} / {number.format(findings.length)}</span>
          </div>
          <span className="clinical-review-progress-caption">{t("clinicalReview.progressCaption")}</span>
        </div>
      </header>

      <ol className="clinical-review-list">
        {findings.map((finding, index) => {
          const drugA = finding.drug_a.generic_name;
          const drugB = finding.drug_b.generic_name;
          const reviewed = reviewedIds.has(finding.id);
          return (
            <li className={`clinical-review-item${reviewed ? " is-reviewed" : ""}`} key={finding.id}>
              <span className="clinical-review-number" aria-hidden="true">{number.format(index + 1)}</span>
              <div className="clinical-review-content">
                <div className="clinical-review-item-head">
                  <h3>{drugA} + {drugB}</h3>
                  <div className="clinical-review-badges">
                    <SeverityBadge severity={finding.severity} />
                    <VerificationBadge status={finding.verification_status} />
                  </div>
                </div>
                <p>{t(promptFor(finding), { a: drugA, b: drugB })}</p>
                <div className="clinical-review-actions">
                  <a className="clinical-review-link" href={`#finding-${finding.id}`}
                    aria-label={t("clinicalReview.openFinding", { a: drugA, b: drugB })}>
                    {t("clinicalReview.viewFinding")}
                    <span aria-hidden="true"> →</span>
                  </a>
                  <label className="clinical-review-toggle">
                    <input type="checkbox" checked={reviewed} onChange={() => toggleReviewed(finding.id)} />
                    <span>{t("clinicalReview.markReviewed")}</span>
                  </label>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
