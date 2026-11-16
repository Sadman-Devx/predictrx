import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { StateBlock } from "../components/ui/StateBlock";
import { useI18n, type MessageKey } from "../i18n";

interface Props {
  titleKey: MessageKey;
  hintKey?: MessageKey;
  /** Optional link so a not-yet-built screen never becomes a dead end. */
  actionTo?: string;
  actionKey?: MessageKey;
}

/** A screen that has no content of its own yet. It says so, explains what to do instead, and always offers a way forward. */
export function Placeholder({ titleKey, hintKey, actionTo, actionKey }: Props) {
  const { t } = useI18n();
  return (
    <section>
      <PageHeader title={t(titleKey)} />
      <StateBlock
        kind="empty"
        title={hintKey ? t(titleKey) : t("common.todo")}
        action={
          actionTo && actionKey ? (
            <Link to={actionTo} className="btn">{t(actionKey)}</Link>
          ) : undefined
        }
      >
        {hintKey && <p>{t(hintKey)}</p>}
      </StateBlock>
    </section>
  );
}