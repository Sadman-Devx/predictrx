import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui/PageHeader";
import { StateBlock } from "../components/ui/StateBlock";
import { useI18n } from "../i18n";

/** Any address that matches no screen. The menu stays on the side, so this is never a dead end. */
export default function NotFound() {
  const { t } = useI18n();
  return (
    <section>
      <PageHeader title={t("notfound.title")} />
      <StateBlock
        kind="empty"
        title={t("notfound.title")}
        action={<Link to="/" className="btn">{t("notfound.home")}</Link>}
      >
        <p>{t("notfound.text")}</p>
      </StateBlock>
    </section>
  );
}