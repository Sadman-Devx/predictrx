import { useI18n } from "../../i18n";
import type { Severity } from "../../lib/types";

const COLOR: Record<Severity, string> = {
  major: "var(--sev-major)",
  moderate: "var(--sev-moderate)",
  minor: "var(--sev-minor)",
  unknown: "var(--sev-unknown)",
};

// Distinct SHAPES so severity is never signalled by colour alone.
function Icon({ severity }: { severity: Severity }) {
  const common = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true as const, fill: "currentColor" };
  switch (severity) {
    case "major":
      return <svg {...common}><path d="M6 1 11.5 11h-11z" /></svg>;
    case "moderate":
      return <svg {...common}><path d="M6 0.5 11.5 6 6 11.5 0.5 6z" /></svg>;
    case "minor":
      return <svg {...common}><circle cx="6" cy="6" r="5" /></svg>;
    default:
      return <svg {...common}><rect x="1.5" y="1.5" width="9" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
  }
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { t } = useI18n();
  return (
    <span className="badge" style={{ color: COLOR[severity] }}>
      <Icon severity={severity} />
      {t(`severity.${severity}`)}
    </span>
  );
}
