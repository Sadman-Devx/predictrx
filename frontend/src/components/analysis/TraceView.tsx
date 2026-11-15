import "../../styles/results.css";
import { useI18n, type MessageKey } from "../../i18n";
import { formatJson, toolName } from "../../lib/results";
import type { AgentTraceStep, PipelineAgent } from "../../lib/types";

const TITLE: Record<PipelineAgent, MessageKey> = {
  resolver: "analysis.step.resolver.title",
  clinical_notes: "analysis.step.clinical_notes.title",
  drug_interaction: "analysis.step.drug_interaction.title",
  advisory: "analysis.step.advisory.title",
  verifier: "analysis.step.verifier.title",
};

function isAgent(name: string): name is PipelineAgent {
  return Object.prototype.hasOwnProperty.call(TITLE, name);
}

/**
 * Agent trace tab: which agent ran, what it read and wrote (redacted summaries), which tools it called, how long it took.
 * Nothing is invented here: every line comes from the trace rows the server stored with the run.
 */
export function TraceView({ trace, traceKnown }: { trace: AgentTraceStep[]; traceKnown: boolean }) {
  const { t } = useI18n();

  const time = (ms: number): string =>
    ms < 1000 ? t("analysis.latency.ms", { n: Math.round(ms) }) : t("analysis.latency.s", { n: (ms / 1000).toFixed(1) });

  const total = trace.reduce((sum, s) => sum + (s.latency_ms > 0 ? s.latency_ms : 0), 0);

  return (
    <div className="card">
      <h2>{t("trace.title")}</h2>
      <p className="muted small">{t("trace.note")}</p>

      {trace.length === 0 ? (
        <p className="muted" role="status">{traceKnown ? t("trace.empty") : t("analysis.trace.unavailable")}</p>
      ) : (
        <>
          {total > 0 && <p className="small muted">{t("trace.total", { time: time(total) })}</p>}
          <ol className="trace-list">
            {trace.map((step, i) => {
              const calls = step.tool_calls ?? [];
              return (
                <li key={`${step.agent_name}-${step.step_order}-${i}`} className="trace-step">
                  <div className="trace-head">
                    <h3>
                      {i + 1}. {isAgent(step.agent_name) ? t(TITLE[step.agent_name]) : step.agent_name}
                    </h3>
                    {step.latency_ms > 0 && <span className="muted small">{time(step.latency_ms)}</span>}
                  </div>

                  {step.input_summary && (
                    <div>
                      <p className="trace-label">{t("trace.input")}</p>
                      <p className="trace-text">{step.input_summary}</p>
                    </div>
                  )}

                  {step.output_summary && (
                    <div>
                      <p className="trace-label">{t("trace.output")}</p>
                      <p className="trace-text">{step.output_summary}</p>
                    </div>
                  )}

                  <div>
                    <p className="trace-label">{t("trace.tools")}</p>
                    {calls.length === 0 ? (
                      <p className="muted small trace-text">{t("trace.noTools")}</p>
                    ) : (
                      <>
                        <ul className="trace-tools">
                          {calls.map((call, j) => (
                            <li key={j} className="trace-tool">{toolName(call)}</li>
                          ))}
                        </ul>
                        <details>
                          <summary>{t("trace.rawCalls")}</summary>
                          <pre className="trace-json">{formatJson(calls)}</pre>
                        </details>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}