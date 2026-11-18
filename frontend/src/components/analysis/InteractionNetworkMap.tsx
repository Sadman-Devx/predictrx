import { useMemo } from "react";
import "../../styles/interaction-map.css";
import { useI18n, type MessageKey } from "../../i18n";
import type { InteractionMap as InteractionMapData, Severity, VerificationStatus } from "../../lib/types";

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

const NODE_WIDTH = 164;
const NODE_HEIGHT = 68;
const CELL_WIDTH = 205;
const CELL_HEIGHT = 116;
const MARGIN = 32;

function shortLabel(label: string): string {
  const clean = label.trim();
  const chars = Array.from(clean);
  return chars.length > 22 ? `${chars.slice(0, 21).join("")}…` : clean || "—";
}

export function InteractionNetworkMap({ map }: { map: InteractionMapData }) {
  const { t, lang } = useI18n();
  const locale = lang === "bn" ? "bn-BD" : "en-GB";

  const orderedNodes = useMemo(() => {
    const degree = new Map<string, number>();
    for (const edge of map.edges) {
      degree.set(edge.source_node_id, (degree.get(edge.source_node_id) ?? 0) + 1);
      degree.set(edge.target_node_id, (degree.get(edge.target_node_id) ?? 0) + 1);
    }
    return [...map.nodes].sort(
      (a, b) =>
        (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) ||
        (a.state === b.state ? 0 : a.state === "matched" ? -1 : 1) ||
        a.label.localeCompare(b.label),
    );
  }, [map]);

  const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(orderedNodes.length))));
  const rows = Math.ceil(orderedNodes.length / columns);
  const width = Math.max(360, MARGIN * 2 + NODE_WIDTH + (columns - 1) * CELL_WIDTH);
  const height = Math.max(220, MARGIN * 2 + NODE_HEIGHT + (rows - 1) * CELL_HEIGHT);
  const positions = new Map(
    orderedNodes.map((node, index) => [
      node.id,
      {
        x: MARGIN + NODE_WIDTH / 2 + (index % columns) * CELL_WIDTH,
        y: MARGIN + NODE_HEIGHT / 2 + Math.floor(index / columns) * CELL_HEIGHT,
      },
    ]),
  );
  const edgeGroups = new Map<string, InteractionMapData["edges"]>();
  for (const edge of map.edges) {
    const key = [edge.source_node_id, edge.target_node_id].sort().join(":");
    const group = edgeGroups.get(key) ?? [];
    group.push(edge);
    edgeGroups.set(key, group);
  }
  const edgeOffsets = new Map<number, number>();
  for (const group of edgeGroups.values()) {
    group.forEach((edge, index) => edgeOffsets.set(edge.finding_id, (index - (group.length - 1) / 2) * 12));
  }
  const number = new Intl.NumberFormat(locale);

  return (
    <section className="card interaction-map" aria-labelledby="interaction-map-title">
      <div className="interaction-map-heading">
        <div>
          <h2 id="interaction-map-title">{t("interactionMap.title")}</h2>
          <p className="muted small">{t("interactionMap.subtitle")}</p>
        </div>
        <span className="interaction-map-count">
          {t("interactionMap.count", {
            medicines: number.format(map.nodes.length),
            findings: number.format(map.edges.length),
          })}
        </span>
      </div>

      <div className="interaction-map-legend" role="group" aria-label={t("interactionMap.severityLegend")}>
        {(["major", "moderate", "minor", "unknown"] as Severity[]).map((severity) => (
          <span key={severity} className="interaction-map-legend-item">
            <span className={`interaction-map-legend-line severity-${severity}`} aria-hidden="true" />
            {t(SEVERITY_LABEL[severity])}
          </span>
        ))}
      </div>
      <div className="interaction-map-legend" role="group" aria-label={t("interactionMap.verificationLegend")}>
        {(["verified", "unverified", "conflict"] as VerificationStatus[]).map((status) => (
          <span key={status} className="interaction-map-legend-item">
            <span className={`interaction-map-legend-line verification-${status}`} aria-hidden="true" />
            {t(VERIFICATION_LABEL[status])}
          </span>
        ))}
      </div>

      {orderedNodes.length === 0 ? (
        <p className="muted interaction-map-empty">{t("interactionMap.noMedicines")}</p>
      ) : (
        <div className="interaction-map-scroll">
          <svg
            className="interaction-map-svg"
            viewBox={`0 0 ${width} ${height}`}
            role="group"
            aria-label={t("interactionMap.graphLabel")}
          >
            {map.edges.map((edge) => {
              const from = positions.get(edge.source_node_id);
              const to = positions.get(edge.target_node_id);
              if (!from || !to) return null;
              const a = orderedNodes.find((node) => node.id === edge.source_node_id);
              const b = orderedNodes.find((node) => node.id === edge.target_node_id);
              if (!a || !b) return null;
              const distance = Math.max(1, Math.hypot(to.x - from.x, to.y - from.y));
              const offset = edgeOffsets.get(edge.finding_id) ?? 0;
              const offsetX = (-(to.y - from.y) / distance) * offset;
              const offsetY = ((to.x - from.x) / distance) * offset;
              const x1 = from.x + offsetX;
              const y1 = from.y + offsetY;
              const x2 = to.x + offsetX;
              const y2 = to.y + offsetY;
              const x = (from.x + to.x) / 2 + offsetX;
              const y = (from.y + to.y) / 2 + offsetY;
              const label = t("interactionMap.edgeLabel", {
                from: a.label,
                to: b.label,
                id: number.format(edge.finding_id),
                severity: t(SEVERITY_LABEL[edge.severity]),
                verification: t(VERIFICATION_LABEL[edge.verification_status]),
                count: number.format(edge.evidence_count),
              });
              return (
                <g
                  key={edge.finding_id}
                  className={`interaction-map-edge severity-${edge.severity} verification-${edge.verification_status}`}
                >
                  <a href={`#finding-${edge.finding_id}`} aria-label={label}>
                    <title>{label}</title>
                    <line className="interaction-map-edge-hit" x1={x1} y1={y1} x2={x2} y2={y2} />
                    <line className="interaction-map-edge-line" x1={x1} y1={y1} x2={x2} y2={y2} />
                    <text className="interaction-map-edge-label" x={x} y={y - 7} textAnchor="middle">
                      {t(SEVERITY_LABEL[edge.severity])}
                    </text>
                  </a>
                </g>
              );
            })}

            {orderedNodes.map((node, index) => {
              const x = MARGIN + (index % columns) * CELL_WIDTH;
              const y = MARGIN + Math.floor(index / columns) * CELL_HEIGHT;
              const label = node.label || t("interactionMap.unknownMedicine");
              const details = node.state === "not_checked"
                ? t("interactionMap.notChecked")
                : node.medication_count > 1
                  ? t("interactionMap.duplicateMedicines", { count: number.format(node.medication_count) })
                  : t("interactionMap.matched");
              return (
                <g key={node.id} className={`interaction-map-node state-${node.state}`}>
                  <title>{label}</title>
                  <rect x={x} y={y} width={NODE_WIDTH} height={NODE_HEIGHT} rx="14" />
                  <text className="interaction-map-node-label" x={x + NODE_WIDTH / 2} y={y + 28} textAnchor="middle">
                    {shortLabel(label)}
                  </text>
                  <text className="interaction-map-node-detail" x={x + NODE_WIDTH / 2} y={y + 49} textAnchor="middle">
                    {details}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}

      <p className="muted small interaction-map-safety" role="note">{t("interactionMap.safetyNote")}</p>
    </section>
  );
}
