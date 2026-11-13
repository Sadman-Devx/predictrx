import { useI18n, type MessageKey } from "../../i18n";
import type { ResolveResult } from "../../lib/drugs";
import { StatusPill, type Tone } from "../ui/StatusPill";

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
      <StatusPill tone={tone}>{t(label)}</StatusPill>
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