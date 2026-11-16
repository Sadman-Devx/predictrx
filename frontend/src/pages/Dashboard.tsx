import { Link } from "react-router-dom";
import { StateBlock } from "../components/ui/StateBlock";
import { useI18n } from "../i18n";

export default function Dashboard() {
  const { t } = useI18n();
  return (
    <section>
      <h1>{t("dashboard.title")}</h1>
      <StateBlock
        kind="empty"
        title={t("dashboard.empty")}
        action={<Link to="/scan" className="btn">{t("dashboard.cta")}</Link>}
      >
        <p>{t("dashboard.hint")}</p>
      </StateBlock>
    </section>
  );
}