import { useMemo, useState } from "react";
import "../../styles/interaction-heatmap.css";
import { useI18n, type MessageKey } from "../../i18n";
import {
  confidenceView,
  evidenceSourceName,
  normalizeVerification,
  SEVERITIES,
  type ConfidenceLevel,
} from "../../lib/results";
import type {
  InteractionMap as InteractionMapData,
  InteractionMapEdge,
  RiskFinding,
  Severity,
  VerificationStatus,
} from "../../lib/types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { VerificationBadge } from "./VerificationBadge";

const SEVERITY_LABEL: Record<Severity, MessageKey> = {
  major: "severity.major",
  moderate: "severity.moderate",
  minor: "severity.minor",
  unknown: "severity.unknown",
};

const VERIFICATION_LABEL: Record<VerificationStatus, MessageKey> = {
  verified: "verify.verified",
  unverified: "verify.unverified",
  conflict: "verify.conflict",
};

const LEVEL_LABEL: Record<ConfidenceLevel, MessageKey> = {
  high: "confidence.level.high",
  medium: "confidence.level.medium",
  low: "confidence.level.low",
};

function rankOf(severity: Severity): number {
  const i = SEVERITIES.indexOf(severity);
  return i === -1 ? SEVERITIES.length : i;
}

/** Order-independent key for a pair of node ids. */
function pairKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

function shortLabel(label: string, max = 14): string {
  const chars = Array.from(label.trim());
  return chars.length > max ? `${chars.slice(0, max - 1).join("")}…` : chars.join("") || "—";
}

/** Same four shapes as SeverityBadge: severity is never colour alone. */
function SeverityGlyph({ severity }: { severity: Severity }) {
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

interface ActiveCell {
  key: string;
  a: string;
  b: string;
}

interface Props {
  map: InteractionMapData;
  /** The run's findings: the map edges carry no confidence or source names, so the tooltip joins on finding_id. */
  findings: RiskFinding[];
}

/**
 * Drug x drug matrix. Each cell is the worst severity among the findings of that pair (a count shows when there are
 * several). Hover, focus or tap a cell: its source, confidence and verification appear in the panel below.
 * An empty cell means "no finding returned", never "safe" (rule.md §1).
 */
export function InteractionHeatmap({ map, findings }: Props) {
  const { t, lang } = useI18n();
  const [active, setActive] = useState<ActiveCell | null>(null);
  const number = useMemo(() => new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB"), [lang]);

  const findingById = useMemo(() => new Map(findings.map((f) => [f.id, f])), [findings]);
  const nodeById = useMemo(() => new Map(map.nodes.map((n) => [n.id, n])), [map.nodes]);

  const cells = useMemo(() => {
    const out = new Map<string, InteractionMapEdge[]>();
    for (const edge of map.edges) {
      const key = pairKey(edge.source_node_id, edge.target_node_id);
      const list = out.get(key) ?? [];
      list.push(edge);
      out.set(key, list);
    }
    for (const list of out.values()) {
      list.sort((a, b) => rankOf(a.severity) - rankOf(b.severity) || a.finding_id - b.finding_id);
    }
    return out;
  }, [map.edges]);

  // Riskiest medicines first (top-left), unmatched ones last, so the risky cluster is visible at a glance.
  const nodes = useMemo(() => {
    const worst = new Map<string, number>();
    const count = new Map<string, number>();
    for (const edge of map.edges) {
      for (const id of [edge.source_node_id, edge.target_node_id]) {
        worst.set(id, Math.min(worst.get(id) ?? 99, rankOf(edge.severity)));
        count.set(id, (count.get(id) ?? 0) + 1);
      }
    }
    return [...map.nodes].sort(
      (a, b) =>
        (a.state === b.state ? 0 : a.state === "matched" ? -1 : 1) ||
        (worst.get(a.id) ?? 99) - (worst.get(b.id) ?? 99) ||
        (count.get(b.id) ?? 0) - (count.get(a.id) ?? 0) ||
        a.label.localeCompare(b.label),
    );
  }, [map]);

  const nameOf = (id: string): string => (nodeById.get(id)?.label ?? "").trim() || t("interactionMap.unknownMedicine");
  const activeEdges = active ? cells.get(active.key) : undefined;

  return (
    <section className="card heatmap" aria-labelledby="heatmap-title">
      <div className="heatmap-heading">
        <div>
          <h2 id="heatmap-title">{t("insights.heatmap.title")}</h2>
          <p className="muted small">{t("insights.heatmap.subtitle")}</p>
        </div>
        <span className="heatmap-count">
          {t("interactionMap.count", {
            medicines: number.format(map.nodes.length),
            findings: number.format(map.edges.length),
          })}
        </span>
      </div>

      <div className="heatmap-legend" role="group" aria-label={t("interactionMap.severityLegend")}>
        {SEVERITIES.map((s) => (
          <span key={s} className={`heatmap-legend-item sev-${s}`}>
            <SeverityGlyph severity={s} />
            {t(SEVERITY_LABEL[s])}
          </span>
        ))}
        <span className="heatmap-legend-item legend-empty">{t("insights.heatmap.legend.noFinding")}</span>
        <span className="heatmap-legend-item legend-unchecked">{t("insights.heatmap.legend.notChecked")}</span>
      </div>
      <div className="heatmap-legend" role="group" aria-label={t("interactionMap.verificationLegend")}>
        {(["verified", "unverified", "conflict"] as VerificationStatus[]).map((v) => (
          <span key={v} className={`heatmap-legend-item legend-ver ver-${v}`}>
            {t(VERIFICATION_LABEL[v])}
          </span>
        ))}
      </div>

      {nodes.length === 0 ? (
        <p className="muted heatmap-empty">{t("interactionMap.noMedicines")}</p>
      ) : nodes.length < 2 ? (
        <p className="muted heatmap-empty">{t("insights.heatmap.needTwo")}</p>
      ) : (
        <div className="heatmap-scroll">
          <table className="heatmap-table" aria-label={t("insights.heatmap.tableLabel")}>
            <thead>
              <tr>
                <td className="heatmap-corner" />
                {nodes.map((col) => (
                  <th
                    key={col.id}
                    scope="col"
                    className={`heatmap-col${col.state === "not_checked" ? " is-unchecked" : ""}${
                      active && (active.a === col.id || active.b === col.id) ? " is-active" : ""
                    }`}
                    title={nameOf(col.id)}
                  >
                    {shortLabel(nameOf(col.id))}
                    {col.state === "not_checked" && (
                      <span className="heatmap-tag">{t("insights.heatmap.notCheckedTag")}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {nodes.map((row) => (
                <tr key={row.id}>
                  <th
                    scope="row"
                    className={`heatmap-row${row.state === "not_checked" ? " is-unchecked" : ""}${
                      active && (active.a === row.id || active.b === row.id) ? " is-active" : ""
                    }`}
                    title={nameOf(row.id)}
                  >
                    {shortLabel(nameOf(row.id), 18)}
                    {row.state === "not_checked" && (
                      <span className="heatmap-tag">{t("insights.heatmap.notCheckedTag")}</span>
                    )}
                  </th>
                  {nodes.map((col) => {
                    if (row.id === col.id) return <td key={col.id} className="heatmap-cell heatmap-self" aria-hidden="true" />;

                    const key = pairKey(row.id, col.id);
                    const edges = cells.get(key);
                    const a = nameOf(row.id);
                    const b = nameOf(col.id);

                    if (!edges || edges.length === 0) {
                      const unchecked = row.state === "not_checked" || col.state === "not_checked";
                      return (
                        <td key={col.id} className="heatmap-cell">
                          <div
                            className={unchecked ? "heatmap-unchecked" : "heatmap-none"}
                            role="img"
                            aria-label={t(unchecked ? "insights.heatmap.notCheckedCellLabel" : "insights.heatmap.emptyCellLabel", { a, b })}
                          >
                            {unchecked ? "—" : "·"}
                          </div>
                        </td>
                      );
                    }

                    const worst = edges[0];
                    const ver = normalizeVerification(worst.verification_status);
                    const isActive = active?.key === key;
                    return (
                      <td key={col.id} className="heatmap-cell">
                        <button
                          type="button"
                          className={`heatmap-btn sev-${worst.severity} ver-${ver}${isActive ? " is-active" : ""}`}
                          aria-pressed={isActive}
                          aria-label={t("insights.heatmap.cellLabel", {
                            a,
                            b,
                            severity: t(SEVERITY_LABEL[worst.severity]),
                            verification: t(VERIFICATION_LABEL[ver]),
                            count: number.format(edges.length),
                          })}
                          onMouseEnter={() => setActive({ key, a: row.id, b: col.id })}
                          onFocus={() => setActive({ key, a: row.id, b: col.id })}
                          onClick={() => setActive({ key, a: row.id, b: col.id })}
                        >
                          <SeverityGlyph severity={worst.severity} />
                          <span>{t(SEVERITY_LABEL[worst.severity])}</span>
                          {edges.length > 1 && <span className="heatmap-multi">×{number.format(edges.length)}</span>}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="heatmap-detail" aria-live="polite">
        {!active || !activeEdges ? (
          <p className="muted small heatmap-detail-hint">{t("insights.heatmap.detail.hint")}</p>
        ) : (
          activeEdges.map((edge) => {
            const f = findingById.get(edge.finding_id);
            const ver = normalizeVerification(edge.verification_status);
            const conf = f ? confidenceView(f.confidence) : null;
            const sources = f ? Array.from(new Set(f.evidence.map((item) => evidenceSourceName(item)))) : [];
            return (
              <article key={edge.finding_id} className={`heatmap-detail-item sev-${edge.severity}`}>
                <h3 className="heatmap-detail-pair">
                  {t("insights.heatmap.detail.pair", { a: nameOf(edge.source_node_id), b: nameOf(edge.target_node_id) })}
                </h3>
                <div className="heatmap-detail-badges">
                  <SeverityBadge severity={edge.severity} />
                  <VerificationBadge status={ver} />
                </div>
                <p className="small">
                  <strong>{t("insights.heatmap.detail.confidence")}:</strong>{" "}
                  {conf
                    ? `${number.format(conf.percent)}% (${t(LEVEL_LABEL[conf.level])})`
                    : t("insights.heatmap.detail.noConfidence")}
                </p>
                {/* a confidence value never travels without its basis (rule.md §5) */}
                <p className="muted small">
                  {t("insights.heatmap.detail.basis", {
                    n: number.format(edge.evidence_count),
                    sources: sources.length > 0 ? sources.join(", ") : "—",
                  })}
                </p>
                <a className="heatmap-detail-link small" href={`#finding-${edge.finding_id}`}>
                  {t("insights.heatmap.detail.open")}
                </a>
              </article>
            );
          })
        )}
      </div>

      <p className="muted small heatmap-safety" role="note">{t("insights.heatmap.safetyNote")}</p>
    </section>
  );
}