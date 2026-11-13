import { useI18n, type MessageKey } from "../../i18n";
import type { ResolveResult } from "../../lib/drugs";

const REASON: Record<string, MessageKey> = {
  no_match: "med.reason.no_match",
  ambiguous: "med.reason.ambiguous",
  low_confidence: "med.reason.low_confidence",
  empty_input: "med.reason.invalid",
  input_too_long: "med.reason.invalid",
};

interface Props {
  result: ResolveResult;
  /** Choosing a candidate re-runs the resolver on that name. Never applied automatically. */
  onPickCandidate: (name: string) => void;
}

/** What the resolver found: generic (+ other names) for a match, or the reason and candidates when it did not. */
export function ResolutionDetail({ result, onPickCandidate }: Props) {
  const { t } = useI18n();

  if (result.status === "resolved") {
    return (
      <div className="small">
        {t("med.generic")}: <strong>{result.generic}</strong>
        {result.aliases.length > 0 && <span className="muted"> · {t("med.also")}: {result.aliases.join(", ")}</span>}
        {result.strength_matched === false && <div className="med-warn">{t("med.strengthMismatch")}</div>}
      </div>
    );
  }

  return (
    <div className="small">
      <p>{t(REASON[result.reason] ?? "med.reason.no_match")}</p>
      {result.candidates && result.candidates.length > 0 && (
        <div className="med-candidates">
          {result.candidates.map((c) => (
            <button key={c} type="button" className="btn secondary" onClick={() => onPickCandidate(c)}>
              {t("med.use")} {c}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}