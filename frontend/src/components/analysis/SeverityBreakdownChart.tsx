import "../../styles/severity-chart.css";
import { useI18n } from "../../i18n";
import { SEVERITIES, VERIFICATIONS } from "../../lib/results";
import type { Severity, VerificationStatus } from "../../lib/types";
import { SeverityBadge } from "../ui/SeverityBadge";
import { VerificationBadge } from "./VerificationBadge";

interface Props {
  /** severityCounts(findings) from lib/results.ts */
  severity: Record<Severity, number>;
  /** verificationCounts(findings) from lib/results.ts */
  verification: Record<VerificationStatus, number>;
}

/** Donut radius in a 100x100 viewBox; pathLength=100 on each circle lets a segment length equal its percentage. */
const RADIUS = 38;

function percent(part: number, total: number): number {
  return total > 0 ? Math.round((part / total) * 100) : 0;
}

/**
 * Severity donut + a small verification bar. Both use the counts the Results screen already computes.
 * Colour is never the only signal: every segment has a legend row with a shape badge, a text label and the count.
 */
export function SeverityBreakdownChart({ severity, verification }: Props) {
  const { t, lang } = useI18n();
  const number = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB");

  const sevTotal = SEVERITIES.reduce((sum, s) => sum + severity[s], 0);
  const verTotal = VERIFICATIONS.reduce((sum, v) => sum + verification[v], 0);
  if (sevTotal === 0) return null;

  const visibleSev = SEVERITIES.filter((s) => severity[s] > 0);
  const gap = visibleSev.length > 1 ? 1 : 0; // small visual gap between segments
  let cursor = 0;
  const segments = visibleSev.map((s) => {
    const length = (severity[s] / sevTotal) * 100;
    const seg = { severity: s, length, start: cursor };
    cursor += length;
    return seg;
  });

  const donutLabel =
    t("insights.sevChart.donutLabel") +
    ": " +
    visibleSev
      .map((s) =>
        t("insights.sevChart.segment", {
          label: t(`severity.${s}`),
          n: number.format(severity[s]),
          pct: number.format(percent(severity[s], sevTotal)),
        }),
      )
      .join(", ");

  const visibleVer = VERIFICATIONS.filter((v) => verification[v] > 0);
  const barLabel =
    t("insights.verChart.barLabel") +
    ": " +
    visibleVer
      .map((v) =>
        t("insights.sevChart.segment", {
          label: t(`verify.${v}`),
          n: number.format(verification[v]),
          pct: number.format(percent(verification[v], verTotal)),
        }),
      )
      .join(", ");

  return (
    <section className="sevchart" aria-label={t("insights.sevChart.title")}>
      <div className="sevchart-block">
        <h3 className="sevchart-title">{t("insights.sevChart.title")}</h3>
        <div className="sevchart-donut-row">
          <svg className="sevchart-donut" viewBox="0 0 100 100" role="img" aria-label={donutLabel}>
            <circle className="sevchart-ring-track" cx="50" cy="50" r={RADIUS} />
            {segments.map((seg) => {
              const dash = Math.max(seg.length - gap, 0.01);
              return (
                <circle
                  key={seg.severity}
                  className={`sevchart-seg seg-${seg.severity}`}
                  cx="50"
                  cy="50"
                  r={RADIUS}
                  pathLength={100}
                  strokeDasharray={`${dash} ${100 - dash}`}
                  strokeDashoffset={-seg.start}
                  transform="rotate(-90 50 50)"
                >
                  <title>
                    {t("insights.sevChart.segment", {
                      label: t(`severity.${seg.severity}`),
                      n: number.format(severity[seg.severity]),
                      pct: number.format(percent(severity[seg.severity], sevTotal)),
                    })}
                  </title>
                </circle>
              );
            })}
            <text className="sevchart-total" x="50" y="52" textAnchor="middle">
              {number.format(sevTotal)}
            </text>
            <text className="sevchart-total-label" x="50" y="64" textAnchor="middle">
              {t("insights.sevChart.centerLabel")}
            </text>
          </svg>

          <ul className="sevchart-legend">
            {visibleSev.map((s) => (
              <li key={s} className="sevchart-legend-item">
                <SeverityBadge severity={s} />
                <strong>{number.format(severity[s])}</strong>
                <span className="muted small">{number.format(percent(severity[s], sevTotal))}%</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="sevchart-block">
        <h3 className="sevchart-title">{t("insights.verChart.title")}</h3>
        <div className="sevchart-bar" role="img" aria-label={barLabel}>
          {visibleVer.map((v) => (
            <span
              key={v}
              className={`sevchart-bar-seg ver-${v}`}
              style={{ flexGrow: verification[v] }}
              title={t("insights.sevChart.segment", {
                label: t(`verify.${v}`),
                n: number.format(verification[v]),
                pct: number.format(percent(verification[v], verTotal)),
              })}
            />
          ))}
        </div>
        <ul className="sevchart-legend sevchart-legend-row">
          {visibleVer.map((v) => (
            <li key={v} className="sevchart-legend-item">
              <VerificationBadge status={v} />
              <strong>{number.format(verification[v])}</strong>
            </li>
          ))}
        </ul>
        <p className="muted small sevchart-hint">{t("insights.verChart.hint")}</p>
      </div>
    </section>
  );
}