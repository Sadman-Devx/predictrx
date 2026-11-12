import { useI18n, type MessageKey } from "../../i18n";
import type { ResolveResult } from "../../lib/drugs";

type Tone = "ok" | "warn" | "neutral" | "stop";

function Shape({ tone }: { tone: Tone }) {
  // Distinct shapes: status is never conveyed by colour alone.
  const c = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true as const };
  if (tone === "ok") return <svg {...c}><circle cx="6" cy="6" r="5.25" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M3.4 6.2 5.2 8l3.4-3.6" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
  if (tone === "warn") return <svg {...c}><path d="M6 1 11.5 11h-11z" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
  if (tone === "stop") return <svg {...c}><rect x="1.5" y="1.5" width="9" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.5" /></svg>;
  return <svg {...c}><circle cx="6" cy="6" r="5.25" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.5 2" /></svg>;
}

/** Resolution status + (for resolved items) the confidence WITH its basis — rule.md: never a bare confidence. */
export function ResolveBadge({ result }: { result: ResolveResult }) {
  const { t } = useI18n();

  let tone: Tone;
  let label: MessageKey;
  if (result.status === "unresolved") {
    tone = "stop";
    label = "med.badge.unresolved";
  } else if (result.match_type === "fuzzy") {
    tone = "warn";
    label = "med.badge.fuzzy";
  } else if (result.match_type === "generic") {
    tone = "neutral";
    label = "med.badge.generic";
  } else if (result.verified) {
    tone = "ok";
    label = "med.badge.verified";
  } else {
    tone = "neutral";
    label = "med.badge.unreviewed";
  }

  const basis: Record<string, MessageKey> = { exact: "med.basis.exact", generic: "med.basis.generic", fuzzy: "med.basis.fuzzy" };

  return (
    <span className="resolve">
      <span className={`resolve-badge tone-${tone}`}>
        <Shape tone={tone} />
        {t(label)}
      </span>
      {result.status === "resolved" && (
        <>
          <span className="resolve-basis small muted">
            {Math.round(result.confidence * 100)}% · {t(basis[result.match_type])} · {result.source}
          </span>
          {result.source_ref && (
            <span className="resolve-basis small muted">
              {t("med.source.reference")}:{" "}
              {/^https?:\/\//i.test(result.source_ref) ? (
                <a href={result.source_ref} target="_blank" rel="noreferrer">{result.source_ref}</a>
              ) : result.source_ref}
              {result.source_accessed && ` · ${t("med.source.accessed")}: ${result.source_accessed}`}
            </span>
          )}
        </>
      )}
    </span>
  );
}
