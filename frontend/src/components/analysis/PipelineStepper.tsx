import "../../styles/analysis.css";
import { useI18n, type MessageKey } from "../../i18n";
import type { StepState, StepView } from "../../lib/analysis";
import type { PipelineAgent } from "../../lib/types";

const COPY: Record<PipelineAgent, { title: MessageKey; hint: MessageKey }> = {
  resolver: { title: "analysis.step.resolver.title", hint: "analysis.step.resolver.hint" },
  clinical_notes: { title: "analysis.step.clinical_notes.title", hint: "analysis.step.clinical_notes.hint" },
  drug_interaction: { title: "analysis.step.drug_interaction.title", hint: "analysis.step.drug_interaction.hint" },
  advisory: { title: "analysis.step.advisory.title", hint: "analysis.step.advisory.hint" },
  verifier: { title: "analysis.step.verifier.title", hint: "analysis.step.verifier.hint" },
};

const STATE_TEXT: Record<StepState, MessageKey> = {
  waiting: "analysis.stepstate.waiting",
  running: "analysis.stepstate.running",
  done: "analysis.stepstate.done",
  stopped: "analysis.stepstate.stopped",
  unrecorded: "analysis.stepstate.unrecorded",
};

/** Every state has its own shape AND a text label: status is never shown by colour alone (design.md §2.2). */
function StepGlyph({ state }: { state: StepState }) {
  const common = {
    width: 24,
    height: 24,
    viewBox: "0 0 22 22",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
    focusable: "false" as const,
  };

  switch (state) {
    case "done":
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="8.5" />
          <path d="m7 11.5 3 3 5-6" />
        </svg>
      );
    case "running":
      // The whole icon turns (see analysis.css); with reduced motion it stays a still arc.
      return (
        <svg {...common} className="step-spin">
          <circle cx="11" cy="11" r="8.5" opacity="0.25" />
          <path d="M11 2.5a8.5 8.5 0 0 1 8.5 8.5" />
        </svg>
      );
    case "stopped":
      return (
        <svg {...common}>
          <rect x="3" y="3" width="16" height="16" rx="2" />
          <path d="m8 8 6 6" />
          <path d="m14 8-6 6" />
        </svg>
      );
    case "unrecorded":
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="8.5" strokeDasharray="2 3" />
          <path d="M8 11h6" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="8.5" strokeDasharray="3 3" />
        </svg>
      );
  }
}

export function PipelineStepper({ steps }: { steps: StepView[] }) {
  const { t } = useI18n();

  const latency = (ms: number | null): string | null => {
    if (ms === null || ms <= 0) return null;
    return ms < 1000
      ? t("analysis.latency.ms", { n: Math.round(ms) })
      : t("analysis.latency.s", { n: (ms / 1000).toFixed(1) });
  };

  return (
    <ol className="stepper" aria-label={t("analysis.progress.label")}>
      {steps.map((s, i) => {
        const took = s.state === "done" ? latency(s.latencyMs) : null;
        return (
          <li key={s.agent} className={`step step-${s.state}`} aria-current={s.state === "running" ? "step" : undefined}>
            <span className="step-glyph">
              <StepGlyph state={s.state} />
            </span>
            <div className="step-body">
              <p className="step-title">
                {i + 1}. {t(COPY[s.agent].title)}
              </p>
              <p className="step-hint muted small">{t(COPY[s.agent].hint)}</p>
            </div>
            <span className="step-state">
              {t(STATE_TEXT[s.state])}
              {took && <span className="muted small"> · {took}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}