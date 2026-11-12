import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useI18n, type MessageKey } from "../i18n";
import { DisclaimerStrip } from "./ui/DisclaimerStrip";
import { LanguageToggle } from "./ui/LanguageToggle";

const NAV: { to: string; key: MessageKey }[] = [
  { to: "/", key: "nav.dashboard" },
  { to: "/patients", key: "nav.patients" },
  { to: "/scan", key: "nav.scan" },
  { to: "/medications", key: "nav.medications" },
  { to: "/review", key: "nav.review" },
  { to: "/analysis", key: "nav.analysis" },
  { to: "/twin", key: "nav.twin" },
  { to: "/family", key: "nav.family" },
];

export function AppShell() {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function onLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="shell">
      <a href="#main" className="skip-link">{t("nav.skip")}</a>
      <header className="topbar">
        <NavLink to="/" className="brand">{t("app.name")}</NavLink>
        <nav className="nav" aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}>{t(n.key)}</NavLink>
          ))}
        </nav>
        <span className="user-name">{user?.display_name || user?.email}</span>
        <button type="button" className="btn secondary" onClick={onLogout}>{t("nav.logout")}</button>
        <LanguageToggle />
      </header>
      <main id="main" className="main"><Outlet /></main>
      {/* Persistent on every screen: results pages must never lose the disclaimer. */}
      <DisclaimerStrip />
    </div>
  );
}
