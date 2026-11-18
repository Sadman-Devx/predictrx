import { useId, useState } from "react";
import "../../styles/results.css";
import { useI18n, type MessageKey } from "../../i18n";
import {
  basisSources,
  confidenceView,
  evidenceConfidence,
  evidenceLink,
  evidenceMeta,
  evidenceSourceName,
  normalizeVerification,
} from "../../lib/results";
import type { ConfidenceBasis, EvidenceItem, VerificationStatus } from "../../lib/types";

const VERIFY_LABEL: Record<VerificationStatus, MessageKey> = {
  verified: "verify.verified",
  unverified: "verify.unverified",
  conflict: "verify.conflict",
};

function DocIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M8 13h8" />
      <path d="M8 17h5" />
    </svg>
  );
}

/**
 * Number of sources behind a finding, shown right next to the severity badge.
 * Zero is shown too ("No sources"): an unknown pair with no record must look different from one that has sources.
 */
export function EvidenceCountBadge({ count }: { count: number }) {
  const { t } = useI18n();
  const text =
    count === 0 ? t("evidence.count.none") : count === 1 ? t("evidence.count.one") : t("evidence.count.many", { n: count });
  return (
    <span className={`ev-count${count === 0 ? " is-empty" : ""}`}>
      <DocIcon />
      {text}
    </span>
  );
}

function EvidenceRow({ item, fallback }: { item: EvidenceItem; fallback: number }) {
  const { t } = useI18n();
  const name = evidenceSourceName(item);
  const link = evidenceLink(item);
  const meta = evidenceMeta(item);
  const excerpt = (item.excerpt ?? "").trim();
  const license = (item.license_note ?? "").trim();
  const { percent, level } = confidenceView(evidenceConfidence(item, fallback));
  const levelText = t(`confidence.level.${level}`);

  return (
    <li className={`ev-item${item.available ? "" : " is-missing"}`}>
      <div className="ev-item-head">
        {link ? (
          <a className="ev-src" href={link} target="_blank" rel="noreferrer noopener">
            {name}
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <path d="M15 3h6v6" />
              <path d="M10 14 21 3" />
            </svg>
            <span className="sr-only"> ({t("evidence.newTab")})</span>
          </a>
        ) : (
          <span className="ev-src">{name}</span>
        )}
        {item.id !== null && item.id !== undefined && <span className="muted small">#{item.id}</span>}
      </div>

      {meta && <p className="muted small ev-meta">{meta}</p>}

      {!item.available && (
        <p className="finding-note note-warn" role="note">
          {t("evidence.missing.note")}
        </p>
      )}

      {excerpt ? (
        // The quote is copied from the source (English label / interaction text), so it is marked lang="en".
        <blockquote className="ev-excerpt" lang="en">
          <span className="sr-only">{t("evidence.excerpt.label")}: </span>
          {excerpt}
        </blockquote>
      ) : (
        item.available && <p className="muted small">{t("evidence.excerpt.none")}</p>
      )}

      <div className="ev-conf">
        <div className="ev-conf-head">
          <span className="confidence-label">{t("confidence.title")}</span>
          <strong>{percent}%</strong>
          <span className="muted small">{levelText}</span>
        </div>
        <div
          className="confidence-bar"
          role="meter"
          aria-label={t("confidence.title")}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-valuetext={`${percent}% · ${levelText}`}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
      </div>

      {license && (
        <p className="muted small ev-meta">
          {t("evidence.license")}: {license}
        </p>
      )}
    </li>
  );
}

interface PanelProps {
  evidence: EvidenceItem[];
  /** The finding's own confidence (0..1): used for a source that came without one. */
  confidence: number;
  /** A confidence is never shown without its basis: how many sources, which ones, and the verification result. */
  basis: ConfidenceBasis;
}

/**
 * "Why are we saying this?" under a finding: an Evidence button that expands to the sources behind the warning.
 * Each source shows its name (a link when one is known), a short quote from it and a confidence bar.
 * Conflict findings can still open the lens with an explicit unavailable state when no evidence is attached.
 */
export function EvidencePanel({ evidence, confidence, basis }: PanelProps) {
  const { t } = useI18n();
  const uid = useId();
  const [open, setOpen] = useState(false);
  const panelId = `${uid}-evidence`;
  const isConflict = normalizeVerification(basis.verification_status) === "conflict";

  if (evidence.length === 0 && !isConflict) return null;

  const basisText = evidence.length > 0
    ? t(evidence.length === 1 ? "confidence.basis.one" : "confidence.basis.many", {
        n: evidence.length,
        sources: basisSources(basis),
      })
    : "";

  return (
    <div className="ev">
      <button
        type="button"
        className="ev-toggle"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((cur) => !cur)}
      >
        <DocIcon />
        {t(isConflict ? "evidence.compareButton" : "evidence.button")}
        <svg className="ev-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div id={panelId} className="ev-panel" role="region" aria-label={t("evidence.panel.label")}>
          <p className="ev-panel-title">{t(isConflict ? "evidence.conflictTitle" : "evidence.panel.title")}</p>
          {isConflict && (
            <p className="ev-compare-note" role="note">
              {t(evidence.length > 1 ? "evidence.conflictCompareNote" : "evidence.conflictSingleNote")}
            </p>
          )}
          {evidence.length > 0 ? (
            <ul className={`ev-list${isConflict ? " ev-list-compare" : ""}`}>
              {evidence.map((item, i) => (
                <EvidenceRow key={`${item.type}-${item.id ?? "x"}-${i}`} item={item} fallback={confidence} />
              ))}
            </ul>
          ) : (
            <p className="finding-note note-warn" role="note">{t("evidence.conflictUnavailable")}</p>
          )}
          {evidence.length > 0 && (
            <>
              <p className="muted small ev-foot">
                {basisText} · {t(VERIFY_LABEL[normalizeVerification(basis.verification_status)])}
              </p>
              <p className="muted small ev-foot">{t("evidence.confidence.note")}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}