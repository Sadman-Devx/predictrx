import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { StateBlock } from "../components/ui/StateBlock";
import { StatusPill, type Tone } from "../components/ui/StatusPill";
import { Tabs } from "../components/ui/Tabs";
import { useI18n, type MessageKey } from "../i18n";
import {
  ci,
  getEvalDashboard,
  pct,
  type CaseOutcome,
  type EvalDashboard,
  type EvalRate,
  type EvalSplitBlock,
} from "../lib/evaluation";
import { formatWhen } from "../lib/format";
import "../styles/evaluation.css";

type CaseFilter = "all" | "fail" | "pass";

const OUTCOME_TEXT: Record<CaseOutcome, MessageKey> = {
  match: "eval.outcome.match",
  missed: "eval.outcome.missed",
  false_alarm: "eval.outcome.false_alarm",
  severity_mismatch: "eval.outcome.severity_mismatch",
};
const SEV_TEXT: Record<string, MessageKey> = {
  none: "eval.sev.none",
  unknown: "eval.sev.unknown",
  minor: "eval.sev.minor",
  moderate: "eval.sev.moderate",
  major: "eval.sev.major",
};

/** One big number with its k-of-n and 95% interval. `value === null` is "not measurable", never 0% or 100%. */
function Stat({ label, help, rate, note, tone }: { label: string; help: string; rate: EvalRate | null; note?: string; tone?: Tone }) {
  const { t } = useI18n();
  const measurable = !!rate && rate.value !== null && !note;
  return (
    <div className="card eval-stat">
      <p className="eval-stat-label">{label}</p>
      {measurable && rate ? (
        <>
          <p className="eval-stat-value">{pct(rate.value)}</p>
          <div className="eval-bar" aria-hidden="true"><span style={{ width: `${(rate.value ?? 0) * 100}%` }} /></div>
          <p className="eval-stat-sub muted small">
            {t("eval.count", { k: rate.k, n: rate.n })} · {t("eval.ci", { range: ci(rate) })}
          </p>
        </>
      ) : (
        <>
          <p className="eval-stat-value na">{t("eval.notMeasurable")}</p>
          {note && <p className="eval-note muted small">{note}</p>}
        </>
      )}
      <p className="muted small eval-note">{help}</p>
      {tone && measurable && <StatusPill tone={tone}>{label}</StatusPill>}
    </div>
  );
}

function CasesTable({ block }: { block: EvalSplitBlock }) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<CaseFilter>("all");

  if (block.cases_hidden) {
    return <div className="card"><p className="muted">{t("eval.cases.hidden")}</p></div>;
  }
  const all = block.cases ?? [];
  const rows = all.filter((c) => (filter === "all" ? true : filter === "pass" ? c.passed : !c.passed));
  const label = (sev: string) => (SEV_TEXT[sev] ? t(SEV_TEXT[sev]) : sev);

  return (
    <div className="card">
      <h2 className="eval-table-title">{t("eval.cases.title")}</h2>
      <div className="chips" role="group" aria-label={t("eval.cases.filter.label")} style={{ marginBottom: "var(--space-3)" }}>
        {(["all", "fail", "pass"] as CaseFilter[]).map((f) => (
          <button key={f} type="button" className="chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {t(`eval.cases.filter.${f}` as MessageKey)}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <p className="muted">{t("eval.cases.empty")}</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("eval.col.pair")}</th>
                <th scope="col">{t("eval.col.expected")}</th>
                <th scope="col">{t("eval.col.predicted")}</th>
                <th scope="col">{t("eval.col.result")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={`${c.drug_a}|${c.drug_b}`} className={c.passed ? undefined : "eval-row-fail"}>
                  <th scope="row">{c.drug_a} + {c.drug_b}</th>
                  <td>{label(c.expected)}</td>
                  <td>{label(c.predicted)}</td>
                  <td><StatusPill tone={c.passed ? "ok" : "stop"}>{t(OUTCOME_TEXT[c.outcome])}</StatusPill></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SplitPanel({ split, block, data }: { split: "dev" | "test"; block: EvalSplitBlock | null; data: EvalDashboard }) {
  const { t } = useI18n();
  const info = data.set[split];
  const sev = info.by_expected_severity;

  const setLine = (
    <div className="eval-set muted small">
      <p>
        {t("eval.set.line", {
          split: split.toUpperCase(), n: info.n, none: sev.none ?? 0, minor: sev.minor ?? 0,
          moderate: sev.moderate ?? 0, major: sev.major ?? 0,
        })}
        {info.unreviewed > 0 && <> · {t("eval.set.unreviewed", { n: info.unreviewed })}</>}
      </p>
    </div>
  );

  if (!block) {
    return (
      <>
        <StateBlock kind="empty" title={t("eval.noRun.title")}>
          <p>{t("eval.noRun.hint", { split })}</p>
        </StateBlock>
        {setLine}
      </>
    );
  }

  return (
    <>
      <p className="muted small eval-meta">
        {t("eval.runMeta", { id: block.run_id, n: block.n_cases, fp: block.fingerprint })}
      </p>

      {block.caveats.length > 0 && (
        <div className="card eval-callout" role="note">
          <h2>{t("eval.caveats")}</h2>
          <ul>{block.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
        </div>
      )}

      <div className="eval-stats">
        <Stat label={t("eval.metric.recall")} help={t("eval.metric.recall.help")} rate={block.recall} />
        <Stat
          label={t("eval.metric.precision")}
          help={t("eval.metric.precision.help")}
          rate={block.precision}
          note={block.precision_measurable ? undefined : t("eval.precision.none")}
        />
        <Stat label={t("eval.metric.severity")} help={t("eval.metric.severity.help")} rate={block.severity_agreement} />
        <Stat label={t("eval.metric.guardrail")} help={t("eval.metric.guardrail.help")} rate={block.guardrail.pass_rate} />
      </div>

      <CasesTable block={block} />
      {setLine}
    </>
  );
}

/** Route: /evaluation (admin only). Honest numbers from recorded runs; weak results are shown as they are. */
export default function Evaluation() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<EvalDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [tab, setTab] = useState("dev");

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      setData(await getEvalDashboard());
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const audit = data?.guardrail_audit;
  const auditOk = !!audit && audit.severity_without_evidence === 0;

  return (
    <section>
      <PageHeader
        title={t("eval.title")}
        subtitle={t("eval.subtitle")}
        actions={<button type="button" className="btn secondary" onClick={() => void load()} disabled={loading}>{t("eval.refresh")}</button>}
      />

      {failed && (
        <StateBlock kind="error" title={t("eval.error")} onRetry={() => void load()} />
      )}
      {loading && !data && !failed && <StateBlock kind="loading" />}

      {data && audit && (
        <>
          <div className="card eval-guard" role={auditOk ? "status" : "alert"}>
            <StatusPill tone={auditOk ? "ok" : "stop"}>{t("eval.metric.guardrail")}</StatusPill>
            <div>
              <p>{auditOk ? t("eval.guardrail.ok") : t("eval.guardrail.bad", { n: audit.severity_without_evidence })}</p>
              <p className="muted small">
                {t("eval.guardrail.audit", { n: audit.findings_with_severity, total: audit.findings_total })}
              </p>
            </div>
          </div>

          {data.set.warnings.length > 0 && (
            <div className="card eval-callout" role="note">
              <ul>{data.set.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </div>
          )}

          <Tabs
            label={t("eval.tabs.label")}
            active={tab}
            onChange={setTab}
            tabs={[
              { id: "dev", label: t("eval.tab.dev"), panel: <SplitPanel split="dev" block={data.pairs.dev} data={data} /> },
              { id: "test", label: t("eval.tab.test"), panel: <SplitPanel split="test" block={data.pairs.test} data={data} /> },
            ]}
          />

          {data.history.length > 0 && (
            <div className="card eval-foot">
              <h2 className="eval-table-title">{t("eval.history.title")}</h2>
              <ul className="eval-history">
                {data.history.map((h) => (
                  <li key={h.id}>
                    <span>{t("eval.history.row", { id: h.id, split: h.split, status: h.status, n: h.n_cases })}</span>
                    {h.status === "completed" ? (
                      <span className="muted small">
                        {t("eval.history.metrics", { recall: pct(h.recall), precision: pct(h.precision), severity: pct(h.severity_agreement) })}
                        {h.finished_at ? ` · ${formatWhen(h.finished_at, lang)}` : ""}
                      </span>
                    ) : (
                      <span className="muted small">{h.error_code}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="muted small eval-foot">{t("eval.dataNote")}</p>
        </>
      )}
    </section>
  );
}
