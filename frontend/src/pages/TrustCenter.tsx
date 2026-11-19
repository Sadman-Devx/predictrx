import { useEffect, useState } from "react";
import { PageHeader } from "../components/ui/PageHeader";
import { useI18n, type MessageKey } from "../i18n";
import { loadKnowledgeCounts, type KnowledgeCounts } from "../lib/trust";
import "../styles/trust.css";

// Every line below is a statement that can be checked against the code or the docs (rule.md: no claim without a basis).
// Planned items are labelled "planned, not built". Nothing here quotes an accuracy figure.
const LIMITS: MessageKey[] = [
  "trust.limit.coverage",
  "trust.limit.brands",
  "trust.limit.labs",
  "trust.limit.norecord",
  "trust.limit.synthetic",
];

const GUARANTEES: MessageKey[] = [
  "trust.guard.evidence",
  "trust.guard.verifier",
  "trust.guard.norecord",
  "trust.guard.dosing",
  "trust.guard.pii",
  "trust.guard.audit",
];

const PENDING: MessageKey[] = [
  "trust.pending.brands",
  "trust.pending.eval",
  "trust.pending.wording",
  "trust.pending.clinical",
];

const PLANNED: MessageKey[] = [
  "trust.plan.brands",
  "trust.plan.study",
  "trust.plan.licence",
  "trust.plan.vitals",
  "trust.plan.federated",
  "trust.plan.audio",
  "trust.plan.markets",
];

function List({ items }: { items: MessageKey[] }) {
  const { t } = useI18n();
  return (
    <ul className="trust-list">
      {items.map((k) => (
        <li key={k}>{t(k)}</li>
      ))}
    </ul>
  );
}

/** Route: /trust. What PredictRx knows, what it does not, what is still to be verified, and what is only planned. */
export default function TrustCenter() {
  const { t, lang } = useI18n();
  const [counts, setCounts] = useState<KnowledgeCounts | null>(null);

  useEffect(() => {
    let active = true;
    void loadKnowledgeCounts().then((c) => {
      if (active) setCounts(c);
    });
    return () => {
      active = false;
    };
  }, []);

  const number = new Intl.NumberFormat(lang === "bn" ? "bn-BD" : "en-GB");
  const show = (n: number | null | undefined) => (n == null ? t("trust.counts.unavailable") : number.format(n));

  return (
    <section className="trust-page">
      <PageHeader title={t("trust.title")} subtitle={t("trust.subtitle")} />

      <div className="card trust-note" role="note">
        <p>{t("trust.disclaimer")}</p>
      </div>

      <section className="card" aria-labelledby="trust-known">
        <h2 id="trust-known">{t("trust.known.title")}</h2>
        <p className="muted">{t("trust.known.hint")}</p>
        <div className="trust-stats" aria-busy={counts == null}>
          <div className="trust-stat">
            <strong>{counts == null ? t("common.loading") : show(counts.drugs)}</strong>
            <span className="muted small">{t("trust.counts.drugs")}</span>
          </div>
          <div className="trust-stat">
            <strong>{counts == null ? t("common.loading") : show(counts.interactions)}</strong>
            <span className="muted small">{t("trust.counts.interactions")}</span>
          </div>
        </div>
        <p className="muted small">{t("trust.counts.labels")}</p>
        <p className="muted small">{t("trust.counts.note")}</p>
      </section>

      <section className="card" aria-labelledby="trust-limits">
        <h2 id="trust-limits">{t("trust.limit.title")}</h2>
        <List items={LIMITS} />
      </section>

      <section className="card" aria-labelledby="trust-guard">
        <h2 id="trust-guard">{t("trust.guard.title")}</h2>
        <List items={GUARANTEES} />
      </section>

      <section className="card" aria-labelledby="trust-sources">
        <h2 id="trust-sources">{t("trust.sources.title")}</h2>
        <ul className="trust-sources">
          <li>
            <strong>{t("trust.sources.fda.name")}</strong>
            <p>{t("trust.sources.fda.text")}</p>
          </li>
          <li>
            <strong>{t("trust.sources.ddinter.name")}</strong>
            <p>{t("trust.sources.ddinter.text")}</p>
          </li>
          <li>
            <strong>{t("trust.sources.brands.name")}</strong>
            <p>{t("trust.sources.brands.text")}</p>
          </li>
        </ul>
      </section>

      <section className="card" aria-labelledby="trust-pending">
        <h2 id="trust-pending">{t("trust.pending.title")}</h2>
        <p className="muted">{t("trust.pending.hint")}</p>
        <ul className="trust-list">
          {PENDING.map((k) => (
            <li key={k}>
              <span className="trust-tag trust-tag-pending">{t("trust.tag.pending")}</span> {t(k)}
            </li>
          ))}
        </ul>
      </section>

      <section className="card" aria-labelledby="trust-planned">
        <h2 id="trust-planned">{t("trust.plan.title")}</h2>
        <p className="muted">{t("trust.plan.hint")}</p>
        <ul className="trust-list">
          {PLANNED.map((k) => (
            <li key={k}>
              <span className="trust-tag">{t("trust.tag.planned")}</span> {t(k)}
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}