import type { ReactNode } from "react";
import "../../styles/results.css";
import { useI18n } from "../../i18n";
import { enteredAs, normalizeVerification } from "../../lib/results";
import type { FindingView } from "../../lib/types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { EvidenceCountBadge, EvidencePanel } from "./EvidencePanel";
import { VerificationBadge } from "./VerificationBadge";

/**
 * One finding card (design.md §1.4): drug pair (generic + the name as entered), severity with its evidence count,
 * rationale, confidence WITH its basis, an "Evidence" button that expands to the sources (name + link, short quote,
 * confidence bar) and the verification badge.
 *
 * Honest states, never hidden:
 *  - "unknown" with no source  -> "No interaction record found. This does not mean the combination is safe."
 *  - any other severity with no source (the server should never send this) -> a visible warning, not a silent card.
 *  - "unverified" is shown muted with its reason; "conflict" is visually distinct and explained in one sentence.
 *
 * Used by the doctor view (a stored RiskFinding) and by the What-if tab (a simulated finding, which has no database id):
 * both fit `FindingView`. `extra` is an optional block shown at the bottom of the card (the What-if tab puts the source's
 * management note there).
 */
export function FindingCard({ finding, extra, id }: { finding: FindingView; extra?: ReactNode; id?: string }) {
  const { t } = useI18n();

  const status = normalizeVerification(finding.verification_status);
  const evidence = finding.evidence ?? [];
  const a = finding.drug_a.generic_name;
  const b = finding.drug_b.generic_name;

  const entered = [
    ...enteredAs(finding.entered_names_a, a).map((n) => `${n} (${a})`),
    ...enteredAs(finding.entered_names_b, b).map((n) => `${n} (${b})`),
  ];

  const classes = ["finding", `sev-${finding.severity}`];
  if (status === "unverified") classes.push("is-unverified");
  if (status === "conflict") classes.push("is-conflict");

  return (
    <li id={id} className={classes.join(" ")}>
      <div className="finding-head">
        <h3 className="finding-pair">
          <span>{a}</span>
          <span className="finding-plus" aria-hidden="true">+</span>
          <span className="sr-only">{t("finding.and")}</span>
          <span>{b}</span>
        </h3>
        <div className="finding-badges">
          <SeverityBadge severity={finding.severity} />
          <EvidenceCountBadge count={evidence.length} />
          <VerificationBadge status={status} />
        </div>
      </div>

      {entered.length > 0 && (
        <p className="muted small">
          {t("finding.enteredAs")}: {entered.join(" · ")}
        </p>
      )}

      {finding.rationale && <p className="finding-rationale">{finding.rationale}</p>}

      {status === "conflict" && <p className="finding-note note-conflict" role="note">{t("verify.conflict.note")}</p>}
      {status === "unverified" && <p className="finding-note" role="note">{t("verify.unverified.note")}</p>}

      <ConfidenceMeter value={finding.confidence} basis={finding.confidence_basis} />

      {evidence.length > 0 ? (
        <EvidencePanel evidence={evidence} confidence={finding.confidence} basis={finding.confidence_basis} />
      ) : (
        <>
          {status === "conflict" && (
            <EvidencePanel evidence={evidence} confidence={finding.confidence} basis={finding.confidence_basis} />
          )}
          {finding.severity === "unknown" ? (
            <p className="finding-note" role="note">{t("finding.unknown.note")}</p>
          ) : (
            <p className="finding-note note-warn" role="alert">{t("finding.noSource")}</p>
          )}
        </>
      )}

      {extra}
    </li>
  );
}