import "../../styles/results.css";
import { useI18n, type MessageKey } from "../../i18n";
import { normalizeVerification } from "../../lib/results";
import type { VerificationStatus } from "../../lib/types";

const LABEL: Record<VerificationStatus, MessageKey> = {
  verified: "verify.verified",
  unverified: "verify.unverified",
  conflict: "verify.conflict",
};

// Distinct SHAPES as well as colours: status is never conveyed by colour alone (design.md §2.2).
function Glyph({ status }: { status: VerificationStatus }) {
  const c = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true as const, focusable: "false" as const, fill: "none" };
  if (status === "verified")
    return (
      <svg {...c}>
        <circle cx="6" cy="6" r="5.25" stroke="currentColor" strokeWidth="1.5" />
        <path d="M3.4 6.2 5.2 8l3.4-3.6" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    );
  if (status === "conflict")
    return (
      <svg {...c}>
        <circle cx="6" cy="6" r="5.25" stroke="currentColor" strokeWidth="1.5" />
        <path d="M4 4.8h4M4 7.2h4M4.6 9l2.8-6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
      </svg>
    );
  return (
    <svg {...c}>
      <circle cx="6" cy="6" r="5.25" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.5 2" />
    </svg>
  );
}

/** Verified · Unverified · Conflict (design.md §4.6). A value the server did not define is shown as Unverified, never as Verified. */
export function VerificationBadge({ status }: { status: VerificationStatus | string }) {
  const { t } = useI18n();
  const safe = normalizeVerification(status);
  return (
    <span className={`vbadge v-${safe}`}>
      <Glyph status={safe} />
      {t(LABEL[safe])}
    </span>
  );
}