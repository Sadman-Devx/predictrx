import { useI18n, type MessageKey } from "../i18n";

export function Placeholder({ titleKey, hintKey }: { titleKey: MessageKey; hintKey?: MessageKey }) {
  const { t } = useI18n();
  return (
    <section className="card">
      <h1>{t(titleKey)}</h1>
      <p>{hintKey ? t(hintKey) : t("common.todo")}</p>
    </section>
  );
}
