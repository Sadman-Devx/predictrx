import { useI18n } from "../../i18n";

/** Dashed "DEMO DATA" label from the design. The prototype only ever holds synthetic data (rule.md §3, §7). */
export function DemoBadge() {
  const { t } = useI18n();
  return <span className="demo-badge">{t("demo.badge")}</span>;
}