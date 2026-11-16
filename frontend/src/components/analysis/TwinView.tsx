import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import "../../styles/results.css";
import "../../styles/twin.css";
import { useTwin } from "../../hooks/useTwin";
import { useI18n } from "../../i18n";
import { resolveMedications, type DrugSuggestion, type UnresolvedMedication } from "../../lib/drugs";
import { formatWhen, pickLangText } from "../../lib/format";
import { enteredAs, SEVERITIES } from "../../lib/results";
import { LIMITATION_KEY } from "../../lib/twin";
import type { Severity, SeverityPicture, TwinScenario, TwinScenarioSummary } from "../../lib/types";
import { DrugAutocomplete } from "../medication/DrugAutocomplete";
import { ResolutionDetail } from "../medication/ResolutionDetail";
import { SeverityBadge } from "../ui/SeverityBadge";
import { StateBlock } from "../ui/StateBlock";
import { StatusPill } from "../ui/StatusPill";
import { FindingCard } from "./FindingCard";

interface Props {
  /** The completed analysis this simulation starts from. It is never changed by anything done here. */
  runId: number;
  /** True while the What-if tab is the open one. The history is requested the first time it opens (the read is audited). */
  active: boolean;
  /** Generic names of the medicines in the base analysis: a duplicate is refused here before the server is asked. */
  baseGenerics: string[];
}

/** The medicine the person is about to test. `generic` is what the server receives; nothing is guessed on the way. */
interface Choice {
  generic: string;
  /** What the person picked or typed (a brand, or the generic itself). */
  entered: string;
  kind: "generic" | "brand" | "possible";
  /** False for a brand-to-generic match that no pharmacist has reviewed yet: said out loud, never hidden. */
  reviewed: boolean;
  /** A "possible" (spelling-similar) match must be confirmed by the person before it can be run. */
  confirmed: boolean;
}

/**
 * What-if tab (Day 10, the Digital Twin of docs/PRD.md §3.5): "if this medicine is added, how does the interaction picture change?"
 *
 * Rules kept on this screen (docs/rule.md, docs/design.md §1.7):
 *  - It is a SIMULATION FOR EXPLORATION, said at the top and again in the result. It is never a prediction and never advice.
 *  - Nothing is written to the patient's record: the base analysis and the medicine list stay exactly as they were.
 *  - Same evidence chips, confidence-with-basis, verification badges and honest states as the main results (FindingCard).
 *  - "No record" is never "safe". A pair without an interaction record is listed as "unknown" with that sentence.
 *  - A brand name is never guessed: a possible match must be confirmed, an unrecognised name offers candidates to choose from.
 *  - What the simulation does NOT use (labs, vitals, label text) is listed on the result.
 */
export function TwinView({ runId, active, baseGenerics }: Props) {
  const { t, lang } = useI18n();
  const [opened, setOpened] = useState(false);
  const twin = useTwin(runId, opened);

  useEffect(() => {
    if (active) setOpened(true);
  }, [active]);

  // ---- choosing the medicine to test ----
  const [choice, setChoice] = useState<Choice | null>(null);
  const [lookup, setLookup] = useState<"idle" | "checking" | "error">("idle");
  const [unresolved, setUnresolved] = useState<UnresolvedMedication | null>(null);
  const lookupTicket = useRef(0);
  const lastText = useRef("");

  const baseSet = useMemo(() => new Set(baseGenerics.map((g) => g.trim().toLowerCase())), [baseGenerics]);
  const duplicate = choice ? baseSet.has(choice.generic.trim().toLowerCase()) : false;
  const busy = twin.busy !== "idle";
  const canRun = !!choice && choice.confirmed && !duplicate && !busy && lookup !== "checking";

  function pick(s: DrugSuggestion) {
    lookupTicket.current += 1;
    twin.clearError();
    setUnresolved(null);
    setLookup("idle");
    setChoice({
      generic: s.generic,
      entered: s.name,
      kind: s.type === "brand" ? "brand" : "generic",
      reviewed: s.type === "generic" || s.verified,
      confirmed: true,
    });
  }

  /** Free text: the resolver decides (exact / generic / spelling-similar / not recognised). Never applied silently. */
  async function checkText(text: string) {
    const ticket = ++lookupTicket.current;
    lastText.current = text;
    twin.clearError();
    setChoice(null);
    setUnresolved(null);
    setLookup("checking");
    try {
      const { results } = await resolveMedications([{ name: text }]);
      if (lookupTicket.current !== ticket) return;
      const r = results[0];
      if (!r) {
        setLookup("error");
        return;
      }
      setLookup("idle");
      if (r.status === "resolved") {
        const possible = r.match_type === "fuzzy";
        setChoice({
          generic: r.generic,
          entered: text,
          kind: possible ? "possible" : r.match_type === "exact" ? "brand" : "generic",
          reviewed: r.match_type === "generic" ? true : r.verified,
          confirmed: !possible,
        });
      } else {
        setUnresolved(r);
      }
    } catch {
      if (lookupTicket.current !== ticket) return;
      setLookup("error");
    }
  }

  function clearChoice() {
    lookupTicket.current += 1;
    twin.clearError();
    setChoice(null);
    setUnresolved(null);
    setLookup("idle");
  }

  // ---- moving focus to the result once the person asked for it (so a screen reader reads what changed) ----
  const resultHeading = useRef<HTMLHeadingElement>(null);
  const focusResult = useRef(false);
  useEffect(() => {
    if (twin.scenario && focusResult.current) {
      focusResult.current = false;
      resultHeading.current?.focus();
    }
  }, [twin.scenario]);

  function onRun() {
    if (!choice || !canRun) return;
    focusResult.current = true;
    void twin.run(choice.generic);
  }

  function onOpen(id: number) {
    focusResult.current = true;
    void twin.open(id);
  }

  const scenario = twin.scenario;
  const note = scenario ? pickLangText(scenario.simulation_note.text_bn, scenario.simulation_note.text_en, lang) : null;
  const showsEntered = choice !== null && choice.entered.trim().toLowerCase() !== choice.generic.trim().toLowerCase();

  return (
    <>
      <div className="card twin-banner" role="note">
        <StatusPill tone="neutral">{t("twin.badge")}</StatusPill>
        <p>{note?.text ?? t("twin.simulation.note")}</p>
      </div>

      <div className="twin-grid">
        <div className="twin-main">
          <div className="card twin-picker">
            <h2>{t("twin.picker.title")}</h2>
            <p className="muted">{t("twin.picker.hint")}</p>

            <DrugAutocomplete
              label={t("twin.picker.label")}
              placeholder={t("twin.picker.placeholder")}
              actionLabel={t("twin.picker.find")}
              disabled={twin.busy === "running"}
              onPick={pick}
              onSubmitText={(text) => void checkText(text)}
            />

            {lookup === "checking" && <p className="muted" role="status">{t("med.resolving")}</p>}

            {lookup === "error" && (
              <p className="alert" role="alert">
                {t("med.error")}{" "}
                <button type="button" className="link-btn" onClick={() => void checkText(lastText.current)}>
                  {t("med.retry")}
                </button>
              </p>
            )}

            {unresolved && (
              <div className="twin-unresolved" role="status">
                <p><strong>{unresolved.input}</strong></p>
                <ResolutionDetail result={unresolved} onPickCandidate={(name) => void checkText(name)} />
              </div>
            )}

            {choice && (
              <div className="twin-choice" role="group" aria-label={t("twin.choice.title")}>
                <p className="twin-choice-line">
                  <span className="muted small">{t("twin.choice.title")}</span>
                  <strong>{choice.generic}</strong>
                  {showsEntered && (
                    <span className="muted small">{t("twin.choice.asEntered")}: {choice.entered}</span>
                  )}
                </p>

                {choice.kind === "possible" && !choice.confirmed && (
                  <>
                    <p className="finding-note note-warn" role="note">{t("twin.choice.possible")}</p>
                    <div>
                      <button
                        type="button"
                        className="btn secondary"
                        onClick={() => setChoice({ ...choice, confirmed: true })}
                      >
                        {t("review.confirmMatch")}
                      </button>
                    </div>
                  </>
                )}

                {!choice.reviewed && <p className="muted small">{t("twin.choice.unreviewed")}</p>}

                {duplicate && (
                  <p className="finding-note note-warn" role="alert">
                    {t("twin.choice.alreadyIn", { name: choice.generic })}
                  </p>
                )}

                <div className="twin-actions">
                  <button type="button" className="btn" disabled={!canRun} onClick={onRun}>
                    {twin.busy === "running" ? t("twin.running") : t("twin.run")}
                  </button>
                  <button type="button" className="btn secondary" disabled={twin.busy === "running"} onClick={clearChoice}>
                    {t("twin.choice.clear")}
                  </button>
                </div>
              </div>
            )}

            {twin.errorKey && <p className="alert" role="alert">{t(twin.errorKey)}</p>}
          </div>

          {busy && (
            <StateBlock kind="loading" title={t(twin.busy === "running" ? "twin.loading.run" : "twin.loading.open")} />
          )}

          {!busy && !scenario && (
            <StateBlock kind="empty" title={t("twin.empty.title")}>
              <p>{t("twin.empty.text")}</p>
            </StateBlock>
          )}

          {!busy && scenario && <ScenarioResult scenario={scenario} headingRef={resultHeading} />}
        </div>

        <aside className="twin-side">
          <div className="card">
            <h2>{t("twin.base.title")}</h2>
            {baseGenerics.length === 0 ? (
              <p className="muted">{t("results.medicines.none")}</p>
            ) : (
              <ul className="med-summary">
                {baseGenerics.map((g) => (
                  <li key={g}><strong>{g}</strong></li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <h2>{t("twin.history.title")}</h2>

            {(twin.historyState === "idle" || twin.historyState === "loading") && twin.history.length === 0 && (
              <StateBlock bare kind="loading" />
            )}

            {twin.historyState === "error" && (
              <StateBlock bare kind="error" onRetry={twin.retryHistory}>
                <p>{t("twin.history.error")}</p>
              </StateBlock>
            )}

            {twin.historyState === "ready" && twin.history.length === 0 && (
              <p className="muted">{t("twin.history.empty")}</p>
            )}

            {twin.history.length > 0 && (
              <ul className="twin-history">
                {twin.history.map((row) => (
                  <HistoryRow
                    key={row.scenario_id}
                    row={row}
                    current={scenario?.scenario_id === row.scenario_id}
                    disabled={busy}
                    onOpen={onOpen}
                  />
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------------------------ history row
function HistoryRow({
  row,
  current,
  disabled,
  onOpen,
}: {
  row: TwinScenarioSummary;
  current: boolean;
  disabled: boolean;
  onOpen: (id: number) => void;
}) {
  const { t, lang } = useI18n();
  const when = formatWhen(row.created_at, lang);
  const sev = row.highest_severity_after ? t(`severity.${row.highest_severity_after}`) : t("twin.compare.noneInline");
  return (
    <li>
      <button
        type="button"
        className="twin-hist"
        aria-current={current ? "true" : undefined}
        disabled={disabled}
        onClick={() => onOpen(row.scenario_id)}
      >
        <span className="twin-hist-name">{row.hypothetical_drug.generic_name}</span>
        <span className="muted small">
          {t(row.new_findings_count === 1 ? "twin.history.count.one" : "twin.history.count", { n: row.new_findings_count })}
          {" · "}
          {t("twin.history.highest", { sev })}
        </span>
        {when && <span className="muted small">{when}</span>}
        <span className="twin-hist-open small">{current ? t("twin.history.current") : t("twin.history.open")}</span>
      </button>
    </li>
  );
}

// ------------------------------------------------------------------------------------------------ result
function ScenarioResult({ scenario, headingRef }: { scenario: TwinScenario; headingRef: RefObject<HTMLHeadingElement | null> }) {
  const { t, lang } = useI18n();
  const drug = scenario.hypothetical_drug.generic_name;
  const when = formatWhen(scenario.created_at, lang) || "—";
  const c = scenario.comparison;
  const added = scenario.added_findings;
  const noRecord = scenario.no_record_pairs;

  const label = (s: Severity | null): string => (s ? t(`severity.${s}`) : t("twin.compare.noneInline"));

  return (
    <>
      <div className="card twin-result">
        <h2 ref={headingRef} tabIndex={-1} className="twin-result-title">
          {t("twin.result.title", { drug })}
        </h2>
        <p className="muted small">{t("twin.result.sub", { id: scenario.base_run_id })}</p>

        <div className="twin-compare">
          <PictureColumn title={t("twin.compare.before")} picture={c.before} />
          <PictureColumn title={t("twin.compare.after", { drug })} picture={c.after} />
        </div>

        <p className="twin-change" role="status">
          {c.highest_severity_changed
            ? t("twin.compare.changed", { from: label(c.before.highest_severity), to: label(c.after.highest_severity) })
            : t("twin.compare.unchanged")}
        </p>
        <p className="muted small">
          {t("twin.compare.new", { n: c.new_findings_count })} · {t("twin.compare.pairs", { n: c.pairs_checked })}
        </p>
      </div>

      <section aria-labelledby="twin-added-heading">
        <h2 id="twin-added-heading" className="twin-section-title">{t("twin.added.title", { n: added.length })}</h2>
        {added.length === 0 ? (
          <div className="card"><p>{t("twin.added.none", { drug })}</p></div>
        ) : (
          <ol className="finding-list">
            {added.map((f, i) => (
              <FindingCard
                key={`${f.drug_a.id}-${f.drug_b.id}-${i}`}
                finding={f}
                extra={
                  f.management ? (
                    <div className="twin-mgmt" role="note">
                      <p className="twin-mgmt-title">{t("twin.mgmt.title")}</p>
                      <p>{f.management}</p>
                      <p className="muted small">{t("twin.mgmt.note")}</p>
                    </div>
                  ) : undefined
                }
              />
            ))}
          </ol>
        )}
      </section>

      {noRecord.length > 0 && (
        <div className="card">
          <h2>{t("twin.norecord.title", { n: noRecord.length })}</h2>
          <p className="muted">{t("twin.norecord.hint")}</p>
          <ul className="twin-norecord">
            {noRecord.map((p, i) => {
              const a = p.drug_a.generic_name;
              const b = p.drug_b.generic_name;
              const entered = [
                ...enteredAs(p.entered_names_a, a).map((n) => `${n} (${a})`),
                ...enteredAs(p.entered_names_b, b).map((n) => `${n} (${b})`),
              ];
              return (
                <li key={`${p.drug_a.id}-${p.drug_b.id}-${i}`}>
                  <span className="twin-norecord-pair">
                    <strong>{a}</strong>
                    <span aria-hidden="true"> + </span>
                    <span className="sr-only"> {t("finding.and")} </span>
                    <strong>{b}</strong>
                  </span>
                  <SeverityBadge severity="unknown" />
                  {entered.length > 0 && (
                    <span className="muted small">{t("finding.enteredAs")}: {entered.join(" · ")}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {scenario.gaps.length > 0 && (
        <div className="card notice" role="note">
          <h2>{t("results.gaps.title")}</h2>
          <p>{t("twin.gaps.hint")}</p>
          <ul>
            {scenario.gaps.map((g, i) => (
              <li key={`${g.medication_id}-${i}`}>
                <strong>{g.brand_name || g.raw_text}</strong> —{" "}
                {t(g.reason === "needs_user_selection" ? "results.gap.needs_user_selection" : "results.gap.other")}
              </li>
            ))}
          </ul>
        </div>
      )}

      {scenario.guardrail_violations.length > 0 && (
        <div className="card notice" role="note">
          <h2>{t("results.guardrail.title")}</h2>
          <p>{t("results.guardrail.hint", { n: scenario.guardrail_violations.length })}</p>
          <details>
            <summary>{t("results.guardrail.details")}</summary>
            <ul>
              {scenario.guardrail_violations.map((v, i) => (
                <li key={`${v}-${i}`}><code>{v}</code></li>
              ))}
            </ul>
          </details>
        </div>
      )}

      <div className="card">
        <h2>{t("twin.limits.title")}</h2>
        {scenario.limitations.length === 0 ? (
          <p className="muted">{t("twin.limit.other")}</p>
        ) : (
          <ul className="twin-limits">
            {scenario.limitations.map((code) => (
              <li key={code}>{t(LIMITATION_KEY[code] ?? "twin.limit.other")}</li>
            ))}
          </ul>
        )}
        <p className="muted small">
          {t("twin.stale", { when })}
          {scenario.disclaimer_version ? ` · ${t("results.disclaimerVersion", { v: scenario.disclaimer_version })}` : ""}
        </p>
      </div>
    </>
  );
}

/** One side of the before / after comparison: the highest severity, how many findings, and the count per severity. */
function PictureColumn({ title, picture }: { title: string; picture: SeverityPicture }) {
  const { t } = useI18n();
  const present = SEVERITIES.filter((s) => picture.counts[s] > 0);
  return (
    <div className="twin-col">
      <p className="twin-col-title">{title}</p>
      <div className="twin-col-high">
        <span className="muted small">{t("twin.compare.highest")}</span>
        {picture.highest_severity ? (
          <SeverityBadge severity={picture.highest_severity} />
        ) : (
          // No known severity is NOT "safe": it is said as "no severity recorded", with its own shape.
          <StatusPill tone="neutral">{t("twin.compare.none")}</StatusPill>
        )}
      </div>
      <p className="muted small">{t("twin.compare.findings", { n: picture.total })}</p>
      {present.length > 0 && (
        <div className="count-row" role="group" aria-label={`${t("results.sev.label")}: ${title}`}>
          {present.map((s) => (
            <span key={s} className="count-item">
              <SeverityBadge severity={s} />
              <strong>{picture.counts[s]}</strong>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}