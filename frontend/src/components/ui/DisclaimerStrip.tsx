import { useI18n } from "../../i18n";

export function DisclaimerStrip() {
  const { t } = useI18n();
  return <div className="disclaimer" role="note">{t("disclaimer")}</div>;
}
