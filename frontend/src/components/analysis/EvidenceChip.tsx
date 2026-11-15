import "../../styles/results.css";
import { useI18n } from "../../i18n";
import { chipText, safeHttpUrl, sourceName } from "../../lib/results";
import type { EvidenceItem } from "../../lib/types";

interface ChipProps {
  item: EvidenceItem;
  expanded: boolean;
  /** id of the detail region this chip opens (only referenced while it is open). */
  controls: string;
  onToggle: () => void;
}

/** Source name + record id. One click opens the source details under the finding (design.md §1.1: "see its source in one click"). */
export function EvidenceChip({ item, expanded, controls, onToggle }: ChipProps) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className={`ev-chip${item.available ? "" : " is-missing"}`}
      aria-expanded={expanded}
      aria-controls={expanded ? controls : undefined}
      onClick={onToggle}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M8 13h8" />
        <path d="M8 17h5" />
      </svg>
      {chipText(item)}
      {!item.available && <span className="muted"> · {t("evidence.missing.short")}</span>}
    </button>
  );
}

/** Everything the server knows about one source: where it is from, which part, its reference and its licence. */
export function EvidenceDetail({ item, id }: { item: EvidenceItem; id: string }) {
  const { t } = useI18n();
  const url = safeHttpUrl(item.url);
  const refUrl = safeHttpUrl(item.source_ref);

  return (
    <div id={id} className="ev-detail" role="region" aria-label={t("evidence.detail")}>
      {!item.available && <p className="finding-note note-warn" role="note">{t("evidence.missing.note")}</p>}
      <dl>
        <dt>{t("evidence.source")}</dt>
        <dd>{sourceName(item.source, item.type)}</dd>

        {item.label && (
          <>
            <dt>{t("evidence.record")}</dt>
            <dd>{item.label}</dd>
          </>
        )}

        {item.section && (
          <>
            <dt>{t("evidence.section")}</dt>
            <dd>{item.section}</dd>
          </>
        )}

        {item.source_ref && (
          <>
            <dt>{t("evidence.reference")}</dt>
            <dd>{refUrl ? <a href={refUrl} target="_blank" rel="noreferrer noopener">{item.source_ref}</a> : item.source_ref}</dd>
          </>
        )}

        {item.license_note && (
          <>
            <dt>{t("evidence.license")}</dt>
            <dd>{item.license_note}</dd>
          </>
        )}
      </dl>
      {url && (
        <p className="ev-open">
          <a href={url} target="_blank" rel="noreferrer noopener">{t("evidence.open")}</a>
        </p>
      )}
    </div>
  );
}