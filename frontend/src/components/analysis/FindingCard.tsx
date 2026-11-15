import { useId, useState } from "react";
import "../../styles/results.css";
import { useI18n } from "../../i18n";
import { enteredAs, normalizeVerification } from "../../lib/results";
import type { RiskFinding } from "../../lib/types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { EvidenceChip, EvidenceDetail } from "./EvidenceChip";
import { VerificationBadge } from "./VerificationBadge";

/**
 * One finding card (design.md §1.4): drug pair (generic + the name as entered), severity, rationale, confidence WITH its
 * basis, evidence chips and the verification badge.
 *
 * Honest states, never hidden:
 *  - "unknown" with no source  -> "No interaction record found. This does not mean the combination is safe."
 *  - any other severity with no source (the server should never send this) -> a visible warning, not a silent card.
 *  - "unverified" is shown muted with its reason; "conflict" is visually distinct and explained in one sentence.
 */
export function FindingCard({ finding }: { finding: RiskFinding }) {
  const { t } = useI18n();
  const uid = useId();
  const [open, setOpen] = useState<number | null>(null);

  const status = normalizeVerification(finding.verification_status);
  const evidence = finding.evidence ?? [];
  const a = finding.drug_a.generic_name;
  const b = finding.drug_b.generic_name;

  const entered = [
    ...enteredAs(finding.entered_names_a, a).map((n) => `${n} (${a})`),
    ...enteredAs(finding.entered_names_b, b).map((n) => `${n} (${b})`),
  ];

  const detailId = `${uid}-evidence`;
  const classes = ["finding", `sev-${finding.severity}`];
  if (status === "unverified") classes.push("is-unverified");
  if (status === "conflict") classes.push("is-conflict");

  return (
    <li className={classes.join(" ")}>
      <div className="finding-head">
        <h3 className="finding-pair">
          <span>{a}</span>
          <span className="finding-plus" aria-hidden="true">+</span>
          <span className="sr-only">{t("finding.and")}</span>
          <span>{b}</span>
        </h3>
        <div className="finding-badges">
          <SeverityBadge severity={finding.severity} />
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

      <div className="ev">
        <p className="ev-title">{t("evidence.title")}</p>

        {evidence.length > 0 ? (
          <>
            <ul className="ev-chips">
              {evidence.map((item, i) => (
                <li key={`${item.type}-${item.id ?? "x"}-${i}`}>
                  <EvidenceChip
                    item={item}
                    expanded={open === i}
                    controls={detailId}
                    onToggle={() => setOpen((cur) => (cur === i ? null : i))}
                  />
                </li>
              ))}
            </ul>
            {open !== null && evidence[open] && <EvidenceDetail item={evidence[open]} id={detailId} />}
          </>
        ) : finding.severity === "unknown" ? (
          <p className="finding-note" role="note">{t("finding.unknown.note")}</p>
        ) : (
          <p className="finding-note note-warn" role="alert">{t("finding.noSource")}</p>
        )}
      </div>
    </li>
  );
}