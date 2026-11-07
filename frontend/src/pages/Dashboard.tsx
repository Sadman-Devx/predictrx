import { Link } from "react-router-dom";
import { useI18n } from "../i18n";

export default function Dashboard() {
  const { t } = useI18n();
  return (
    <section className="card">
      <h1>{t("dashboard.title")}</h1>
      <p>{t("dashboard.empty")}</p>
      <Link to="/scan"><button type="button" className="btn">{t("dashboard.cta")}</button></Link>
    </section>
  );
}
