import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { DisclaimerStrip } from "../components/ui/DisclaimerStrip";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useI18n, type MessageKey } from "../i18n";
import { ApiRequestError } from "../lib/api";

function errorKey(err: unknown): MessageKey {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) return "login.network";
    if (err.status === 429) return "login.tooMany";
    if (err.status >= 500) return "login.server";
  }
  return "login.failed"; // 400/401: wrong credentials (never say which one was wrong)
}

export default function Login() {
  const { t } = useI18n();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from} replace />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorKey(err));
      setPassword("");
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <header className="auth-top"><LanguageToggle /></header>

      <main className="auth-main">
        <section className="card auth-card" aria-labelledby="login-title">
          <div className="auth-brand">
            <span className="auth-logo" aria-hidden="true">Rx</span>
            <div>
              <strong>{t("app.name")}</strong>
              <div className="muted">{t("app.tagline")}</div>
            </div>
          </div>

          <h1 id="login-title">{t("login.title")}</h1>
          <p className="muted">{t("login.subtitle")}</p>

          <form onSubmit={onSubmit}>
            <label className="field">
              {t("login.email")}
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="username"
                inputMode="email"
                required
                autoFocus
              />
            </label>

            <label className="field">
              {t("login.password")}
              <span className="pw-wrap">
                <input
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  className="pw-toggle"
                  onClick={() => setShowPw((v) => !v)}
                  aria-pressed={showPw}
                  aria-label={t(showPw ? "login.hide" : "login.show")}
                >
                  <EyeIcon off={showPw} />
                </button>
              </span>
            </label>

            {error && <p className="alert" role="alert">{t(error)}</p>}

            <button type="submit" className="btn block" disabled={busy}>
              {t(busy ? "login.submitting" : "login.submit")}
            </button>
          </form>

          <p className="muted small auth-note">{t("login.privacy")}</p>
        </section>
      </main>

      <DisclaimerStrip />
    </div>
  );
}

function EyeIcon({ off }: { off: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="M3 3l18 18" />}
    </svg>
  );
}