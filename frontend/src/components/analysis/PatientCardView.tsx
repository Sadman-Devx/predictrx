import { useEffect, useState } from "react";
import "../../styles/family.css";
import { usePatientCard } from "../../hooks/usePatientCard";
import { useI18n, type Lang } from "../../i18n";
import { formatWhen, paragraphs } from "../../lib/format";

interface Props {
  runId: number;
  /** True while the "Patient card" tab is the open one. The card is requested the first time it is opened (the read is audited). */
  active: boolean;
}

/**
 * Patient card tab (Day 9). A plain-language explanation for the patient or a caregiver, written from the findings only.
 *
 * Rules (rule.md / design.md): the card never carries dosing or start/stop advice, so the screen repeats that; a person reads it
 * before it is shown to the patient (human in the loop); a missing card is said plainly, never replaced by invented text.
 */
export function PatientCardView({ runId, active }: Props) {
  const { t, lang } = useI18n();
  const [opened, setOpened] = useState(false);
  const { card, state, retry } = usePatientCard(runId, opened);

  useEffect(() => {
    if (active) setOpened(true);
  }, [active]);

  // The card is written in Bangla first. Default to Bangla when it exists, otherwise to whatever the server sent.
  const [chosen, setChosen] = useState<Lang | null>(null);
  const available: Lang[] = card ? (["bn", "en"] as Lang[]).filter((l) => (l === "bn" ? card.text_bn : card.text_en) !== "") : [];
  const shown: Lang | null = chosen && available.includes(chosen) ? chosen : available[0] ?? null;
  const body = card && shown ? (shown === "bn" ? card.text_bn : card.text_en) : "";
  const when = card ? formatWhen(card.generated_at, lang) : "";

  return (
    <div className="card pcard" aria-busy={state === "loading"}>
      <h2>{t("pcard.title")}</h2>

      {(state === "idle" || state === "loading") && <p className="muted" role="status">{t("common.loading")}</p>}

      {state === "error" && (
        <p className="alert" role="alert">
          {t("pcard.error")}{" "}
          <button type="button" className="link-btn" onClick={retry}>{t("common.retry")}</button>
        </p>
      )}

      {state === "unavailable" && <p className="muted">{t("pcard.unavailable")}</p>}

      {state === "empty" && <p className="muted">{t("pcard.empty")}</p>}

      {state === "ready" && card && shown && (
        <>
          <p className="muted">{t("pcard.intro")}</p>

          {available.length > 1 && (
            <div className="chips" role="group" aria-label={t("pcard.lang.label")}>
              {available.map((l) => (
                <button key={l} type="button" className="chip" aria-pressed={shown === l} onClick={() => setChosen(l)}>
                  {l === "bn" ? "বাংলা" : "English"}
                </button>
              ))}
            </div>
          )}

          <div className="pcard-body" lang={shown}>
            {paragraphs(body).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>

          {available.length === 1 && shown !== lang && (
            <p className="muted small">{t(shown === "bn" ? "pcard.onlyBn" : "pcard.onlyEn")}</p>
          )}

          <div className="pcard-notes" role="note">
            <p>{t("pcard.noDose")}</p>
            <p>{t("pcard.review")}</p>
          </div>

          <p className="muted small">
            {[when ? t("pcard.generated", { when }) : "", card.disclaimer_version ? t("results.disclaimerVersion", { v: card.disclaimer_version }) : ""]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </>
      )}
    </div>
  );
}