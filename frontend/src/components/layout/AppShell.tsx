import { NavLink, Outlet } from "react-router-dom";
import { useI18n, type MessageKey } from "../../i18n";
import { DisclaimerStrip } from "../ui/DisclaimerStrip";
import { LanguageToggle } from "../ui/LanguageToggle";

const NAV: { to: string; key: MessageKey }[] = [
  { to: "/", key: "nav.dashboard" },
  { to: "/patients", key: "nav.patients" },
  { to: "/scan", key: "nav.scan" },
  { to: "/analysis", key: "nav.analysis" },
  { to: "/twin", key: "nav.twin" },
  { to: "/family", key: "nav.family" },
];

export function AppShell() {
  const { t } = useI18n();
  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">{t("app.name")}</NavLink>
        <nav className="nav" aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}>{t(n.key)}</NavLink>
          ))}
        </nav>
        <NavLink to="/login" className="nav-login">{t("nav.login")}</NavLink>
        <LanguageToggle />
      </header>
      <main className="main"><Outlet /></main>
      {/* Persistent on every screen: results pages must never lose the disclaimer. */}
      <DisclaimerStrip />
    </div>
  );
}
