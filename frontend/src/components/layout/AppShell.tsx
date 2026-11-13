import { useEffect, useRef, useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { useI18n, type MessageKey } from "../../i18n";
import { BrandMark } from "../ui/BrandMark";
import { DemoBadge } from "../ui/DemoBadge";
import { DisclaimerStrip } from "../ui/DisclaimerStrip";
import { Icon, type IconName } from "../ui/Icon";
import { LanguageToggle } from "../ui/LanguageToggle";

interface NavItem {
  to: string;
  key: MessageKey;
  icon: IconName;
  /** Exact match only (the dashboard at "/"). */
  end?: boolean;
  /** Extra path prefixes that keep this item highlighted (the new-analysis flow spans several screens). */
  also?: string[];
}

// Main navigation exactly as in the design: Dashboard · Patients · New analysis · Analyses.
const NAV: NavItem[] = [
  { to: "/", key: "nav.dashboard", icon: "dashboard", end: true },
  { to: "/patients", key: "nav.patients", icon: "patients" },
  { to: "/scan", key: "nav.scan", icon: "scan", also: ["/medications", "/review"] },
  { to: "/analysis", key: "nav.analysis", icon: "analyses" },
];

function isActive(item: NavItem, pathname: string): boolean {
  if (item.end) return pathname === item.to;
  return [item.to, ...(item.also ?? [])].some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

function initials(name: string): string {
  const parts = name.replace(/\./g, " ").trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((p) => Array.from(p)[0] ?? "");
  return letters.join("").toUpperCase() || "?";
}

function Brand() {
  const { t } = useI18n();
  const name = t("app.name");
  const accent = name.endsWith("Rx");
  return (
    <Link to="/" className="brand">
      <span className="brand-mark"><BrandMark size={36} /></span>
      <span className="brand-name">
        {accent ? name.slice(0, -2) : name}
        {accent && <span className="brand-accent">Rx</span>}
      </span>
    </Link>
  );
}

export function AppShell() {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close the account menu on outside click, Escape, or route change.
  useEffect(() => {
    if (!menuOpen) return;
    function onDown(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  async function onLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  const displayName = user?.display_name || user?.email || "";

  return (
    <div className="shell">
      <a href="#main" className="skip-link">{t("nav.skip")}</a>

      <aside className="sidebar">
        <Brand />
        <nav className="side-nav" aria-label={t("shell.nav.label")}>
          {NAV.map((n) => {
            const active = isActive(n, pathname);
            return (
              <Link key={n.to} to={n.to} className="nav-item" aria-current={active ? "page" : undefined}>
                <Icon name={n.icon} />
                <span>{t(n.key)}</span>
              </Link>
            );
          })}
        </nav>
        <p className="side-foot">{t("shell.footer")}</p>
      </aside>

      <div className="shell-main">
        <header className="topbar">
          <DemoBadge />
          <div className="topbar-right">
            <LanguageToggle />
            {/* Notifications are not built yet: shown disabled, as in the design, never as a working control. */}
            <button type="button" className="icon-btn" disabled aria-label={t("shell.notifications")}>
              <Icon name="bell" />
            </button>
            <div className="user-menu" ref={menuRef}>
              <button
                type="button"
                className="avatar"
                aria-expanded={menuOpen}
                aria-controls="account-menu"
                aria-label={`${t("shell.account")}: ${displayName}`}
                onClick={() => setMenuOpen((v) => !v)}
              >
                {initials(displayName)}
              </button>
              {menuOpen && (
                <div id="account-menu" className="menu-pop">
                  <p className="menu-name">{displayName}</p>
                  {user?.display_name && user.email && <p className="menu-email muted small">{user.email}</p>}
                  <button type="button" className="btn secondary block" onClick={onLogout}>
                    <Icon name="log-out" size={18} />
                    {t("nav.logout")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main id="main" className="main"><Outlet /></main>

        {/* Persistent on every screen: results pages must never lose the disclaimer. */}
        <DisclaimerStrip />
      </div>
    </div>
  );
}