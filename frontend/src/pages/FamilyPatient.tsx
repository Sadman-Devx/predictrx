import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import "../styles/family.css";
import { Icon } from "../components/ui/Icon";
import { PageHeader } from "../components/ui/PageHeader";
import { SeverityBadge } from "../components/ui/SeverityBadge";
import { useFamilySummary } from "../hooks/useFamily";
import { useI18n, type Lang } from "../i18n";
import { formatWhen, paragraphs } from "../lib/format";

/**
 * Family view, step 2 (Day 9, NRB): the read-only latest summary of one shared patient.
 *
 * Plain language only: medicine NAMES (no strengths, no doses), the highest concern level, a short written summary.
 * It never says a medicine is safe, and it always tells the reader to talk to the doctor before changing anything.
 */
export default function FamilyPatient() {
  const { t, lang } = useI18n();
  const { patientId } = useParams();
  const id = Number(patientId);
  const valid = Number.isInteger(id) && id > 0;

  // Hooks cannot be skipped, so an invalid id asks for patient 0, which the server answers with 404 ("gone").
  const { summary, state, retry } = useFamilySummary(valid ? id : 0);
  const [chosen, setChosen] = useState<Lang | null>(null);

  const back = (
    <Link to="/family" className="back-link">
      <Icon name="arrow-left" size={18} />
      {t("family.back")}
    </Link>
  );

  if (state === "loading") {
    return (
      <section>
        {back}
        <p className="muted" role="status">{t("common.loading")}</p>
      </section>
    );
  }

  if (!valid || state === "gone") {
    return (
      <section>
        {back}
        <div className="card empty">
          <p role="alert">{t("family.gone")}</p>
        </div>
      </section>
    );
  }

  if (state === "error" || !summary) {
    return (
      <section>
        {back}
        <div className="card empty">
          <p className="alert" role="alert">{t("family.error")}</p>
          <button type="button" className="btn" onClick={retry}>{t("common.retry")}</button>
        </div>
      </section>
    );
  }

  const available: Lang[] = (["bn", "en"] as Lang[]).filter((l) => (l === "bn" ? summary.text_bn : summary.text_en) !== "");
  const preferred: Lang = chosen ?? lang;
  const shown: Lang | null = available.includes(preferred) ? preferred : available[0] ?? null;
  const body = shown ? (shown === "bn" ? summary.text_bn : summary.text_en) : "";
  const updated = formatWhen(summary.updated_at, lang);

  return (
    <section>
      {back}

      <PageHeader title={summary.patient_code || `#${summary.patient_id}`} subtitle={summary.relationship ? t("family.relationship", { r: summary.relationship }) : undefined} />

      <p className="family-readonly" role="note">{t("family.readOnly")}</p>

      <div className="card family-summary">
        <h2>{t("family.summary.title")}</h2>

        <div className="family-level">
          <span className="muted small">{t("family.severity.label")}</span>
          {summary.severity ? (
            <>
              <SeverityBadge severity={summary.severity} />
              <p className="muted small">{t("family.severity.note")}</p>
            </>
          ) : (
            <p className="muted">{t("family.severity.none")}</p>
          )}
        </div>

        {available.length > 1 && (
          <div className="chips" role="group" aria-label={t("pcard.lang.label")}>
            {available.map((l) => (
              <button key={l} type="button" className="chip" aria-pressed={shown === l} onClick={() => setChosen(l)}>
                {l === "bn" ? "বাংলা" : "English"}
              </button>
            ))}
          </div>
        )}

        {shown ? (
          <div className="pcard-body" lang={shown}>
            {paragraphs(body).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        ) : (
          <p className="muted">{t("family.text.none")}</p>
        )}

        {shown && shown !== lang && available.length === 1 && (
          <p className="muted small">{t(shown === "bn" ? "pcard.onlyBn" : "pcard.onlyEn")}</p>
        )}
      </div>

      <div className="card">
        <h2>{t("family.medicines.title")}</h2>
        {summary.medicines.length === 0 ? (
          <p className="muted">{t("family.medicines.none")}</p>
        ) : (
          <>
            <ul className="family-meds">
              {summary.medicines.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
            <p className="muted small">{t("family.medicines.note")}</p>
          </>
        )}
      </div>

      <div className="pcard-notes" role="note">
        <p>{t("pcard.noDose")}</p>
      </div>

      <p className="muted small">
        {[
          updated ? t("family.updated", { when: updated }) : "",
          summary.consent_granted_by ? t("family.consent", { who: summary.consent_granted_by }) : "",
          summary.disclaimer_version ? t("results.disclaimerVersion", { v: summary.disclaimer_version }) : "",
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
    </section>
  );
}