import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { useI18n, type MessageKey } from "../i18n";

interface Props {
  titleKey: MessageKey;
  hintKey?: MessageKey;
  /** Optional link so a not-yet-built screen never becomes a dead end. */
  actionTo?: string;
  actionKey?: MessageKey;
}

export function Placeholder({ titleKey, hintKey, actionTo, actionKey }: Props) {
  const { t } = useI18n();
  return (
    <section>
      <PageHeader title={t(titleKey)} subtitle={hintKey ? t(hintKey) : undefined} />
      <div className="card">
        <p>{t("common.todo")}</p>
        {actionTo && actionKey && (
          <Link to={actionTo} className="btn secondary">{t(actionKey)}</Link>
        )}
      </div>
    </section>
  );
}