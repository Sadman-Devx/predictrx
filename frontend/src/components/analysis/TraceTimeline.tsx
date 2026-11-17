import "../../styles/analysis.css";
import { useI18n, type MessageKey, type MessageVars } from "../../i18n";
import type { StepState } from "../../lib/analysis";
import type { TimelineStage, TimelineStageKey, TimelineStatus } from "../../lib/types";
import { StepGlyph } from "./PipelineStepper";

const TITLE: Record<TimelineStageKey, MessageKey> = {
  photo_upload: "trace.tl.photo_upload.title",
  ocr: "trace.tl.ocr.title",
  resolve: "trace.tl.resolve.title",
  interaction: "trace.tl.interaction.title",
  guardrail: "trace.tl.guardrail.title",
  report: "trace.tl.report.title",
};

/** Shown while a stage has no result line yet (waiting / running), so a judge sees what the step is for. */
const HINT: Record<TimelineStageKey, MessageKey> = {
  photo_upload: "trace.tl.photo_upload.hint",
  ocr: "trace.tl.ocr.hint",
  resolve: "trace.tl.resolve.hint",
  interaction: "trace.tl.interaction.hint",
  guardrail: "trace.tl.guardrail.hint",
  report: "trace.tl.report.hint",
};

/** Reuses the stepper glyphs: every state keeps its own shape AND a text label (design.md §2.2). */
const GLYPH: Record<TimelineStatus, StepState> = {
  done: "done",
  running: "running",
  failed: "stopped",
  pending: "waiting",
  skipped: "unrecorded",
};

const STATE_TEXT: Record<TimelineStatus, MessageKey> = {
  done: "analysis.stepstate.done",
  running: "analysis.stepstate.running",
  failed: "analysis.stepstate.stopped",
  pending: "analysis.stepstate.waiting",
  skipped: "trace.tl.state.skipped",
};

type Translate = (key: MessageKey, vars?: MessageVars) => string;

/**
 * One line of result per finished stage, built from counts the server sent. Nothing is invented: a missing count means
 * no line (the hint is shown instead). Wording never says a combination is "safe".
 */
function resultLine(stage: TimelineStage, t: Translate): string | null {
  const m = stage.meta;
  if (stage.status === "skipped") {
    return stage.key === "photo_upload" || stage.key === "ocr" ? t("trace.tl.manual") : null;
  }
  if (stage.status !== "done") return null;

  switch (stage.key) {
    case "photo_upload":
      return t("trace.tl.photo_upload.done");
    case "ocr":
      return m.medicines != null ? t("trace.tl.ocr.done", { n: m.medicines }) : null;
    case "resolve":
      return m.total != null ? t("trace.tl.resolve.done", { resolved: m.resolved ?? 0, total: m.total }) : null;
    case "interaction":
      return m.pairs != null ? t("trace.tl.interaction.done", { n: m.pairs }) : null;
    case "guardrail": {
      if (m.verified == null && m.unverified == null && m.conflict == null) return null;
      const vars = { verified: m.verified ?? 0, unverified: m.unverified ?? 0, conflict: m.conflict ?? 0, n: m.violations ?? 0 };
      return t((m.violations ?? 0) > 0 ? "trace.tl.guardrail.doneNotes" : "trace.tl.guardrail.done", vars);
    }
    case "report":
      return t("trace.tl.report.done");
  }
}

/**
 * The "what is the AI doing" timeline: Photo upload → OCR → Brand→Generic → Interaction check → Guardrail → Final report.
 * Each stage shows its state (tick / spinner / stopped), the recorded time and a one-line result.
 * The server sends live statuses while the run works; times and counts arrive when it is completed. A stage without a
 * recorded time (upload, OCR) shows no time at all rather than a guess.
 */
export function TraceTimeline({ stages }: { stages: TimelineStage[] }) {
  const { t } = useI18n();

  const took = (ms: number | null): string | null => {
    if (ms === null || ms <= 0) return null;
    return ms < 1000 ? t("analysis.latency.ms", { n: Math.round(ms) }) : t("analysis.latency.s", { n: (ms / 1000).toFixed(1) });
  };

  return (
    <div className="card">
      <h2>{t("trace.tl.title")}</h2>
      <p className="muted small">{t("trace.tl.note")}</p>
      <ol className="stepper" aria-label={t("trace.tl.title")}>
        {stages.map((s, i) => {
          const line = resultLine(s, t);
          const time = s.status === "done" ? took(s.duration_ms) : null;
          return (
            <li key={s.key} className={`step step-${GLYPH[s.status]}`} aria-current={s.status === "running" ? "step" : undefined}>
              <span className="step-glyph">
                <StepGlyph state={GLYPH[s.status]} />
              </span>
              <div className="step-body">
                <p className="step-title">
                  {i + 1}. {t(TITLE[s.key])}
                </p>
                {line ? <p className="step-summary">{line}</p> : <p className="step-hint muted small">{t(HINT[s.key])}</p>}
              </div>
              <span className="step-state">
                {t(STATE_TEXT[s.status])}
                {time && <span className="muted small"> · {time}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
