import "../../styles/results.css";
import { useI18n, type MessageKey } from "../../i18n";
import { basisSources, confidenceView, normalizeVerification } from "../../lib/results";
import type { ConfidenceBasis, VerificationStatus } from "../../lib/types";

const VERIFY_LABEL: Record<VerificationStatus, MessageKey> = {
  verified: "verify.verified",
  unverified: "verify.unverified",
  conflict: "verify.conflict",
};

interface Props {
  /** 0..1 */
  value: number;
  /** A confidence is never shown without its basis: how many sources, which ones, and the verification result. */
  basis: ConfidenceBasis;
}

export function ConfidenceMeter({ value, basis }: Props) {
  const { t } = useI18n();
  const { percent, level } = confidenceView(value);
  const count = basis.evidence_count ?? 0;

  const basisText =
    count === 0
      ? t("confidence.basis.none")
      : t(count === 1 ? "confidence.basis.one" : "confidence.basis.many", { n: count, sources: basisSources(basis) });

  return (
    <div className="confidence">
      <div className="confidence-head">
        <span className="confidence-label">{t("confidence.title")}</span>
        <strong>{percent}%</strong>
        <span className="muted small">{t(`confidence.level.${level}`)}</span>
      </div>
      <div
        className="confidence-bar"
        role="meter"
        aria-label={t("confidence.title")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${percent}% · ${t(`confidence.level.${level}`)}`}
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      <p className="muted small confidence-basis">
        {basisText} · {t(VERIFY_LABEL[normalizeVerification(basis.verification_status)])}
      </p>
    </div>
  );
}