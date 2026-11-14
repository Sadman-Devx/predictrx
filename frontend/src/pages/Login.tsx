import { useEffect, useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { DisclaimerStrip } from "../components/ui/DisclaimerStrip";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useI18n, type MessageKey } from "../i18n";
import { api, ApiRequestError } from "../lib/api";
import "../styles/auth.css";

type View = "login" | "register";
type Anim = "to-login" | "to-register" | null;
type Notice = { kind: "ok" | "info"; key: MessageKey } | null;

const ANIM_MS = 1100; // keep in sync with --auth-dur in styles/auth.css

function errorKey(err: unknown): MessageKey {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) return "login.network";
    if (err.status === 429) return "login.tooMany";
    if (err.status >= 500) return "login.server";
  }
  return "login.failed"; // 400/401: wrong credentials (never say which one was wrong)
}

function registerErrorKey(err: unknown): MessageKey {
  if (err instanceof ApiRequestError) {
    if (err.status === 0) return "login.network";
    if (err.status === 429) return "login.tooMany";
    if (err.status >= 500) return "login.server";
  }
  return "auth.registerFailed";
}

const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// `inert` works on React 18 and 19 and passes TypeScript: the attribute is
// only rendered (as inert="") when the element should be inert.
const inertIf = (on: boolean) => (on ? ({ inert: "" } as Record<string, unknown>) : {});

export default function Login() {
  const { t, lang } = useI18n();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  // which side is showing, and whether the panel is currently travelling
  const [view, setView] = useState<View>("login");
  const [anim, setAnim] = useState<Anim>(null);
  const [tone, setTone] = useState<"dark" | "light">("light"); // logo colour: light while it sits on the teal panel
  const timers = useRef<number[]>([]);

  // login form
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  // registration form
  const [regName, setRegName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPw, setRegPw] = useState("");
  const [regPw2, setRegPw2] = useState("");
  const [showRegPw, setShowRegPw] = useState(false);
  const [regError, setRegError] = useState<MessageKey | null>(null);
  const [regBusy, setRegBusy] = useState(false);

  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    const list = timers.current;
    return () => list.forEach((id) => window.clearTimeout(id));
  }, []);

  if (user) return <Navigate to={from} replace />;

  function switchTo(next: View) {
    if (anim || next === view) return; // ignore clicks while the panel is travelling
    setError(null);
    setRegError(null);
    setNotice(null);
    if (prefersReducedMotion()) {
      setView(next);
      setTone(next === "login" ? "light" : "dark");
      return;
    }
    setView(next);
    setAnim(next === "login" ? "to-login" : "to-register");
    // the logo changes colour at the moment the stretched panel passes behind it
    timers.current.push(
      window.setTimeout(() => setTone(next === "login" ? "light" : "dark"), ANIM_MS * (next === "login" ? 0.41 : 0.59)),
      window.setTimeout(() => setAnim(null), ANIM_MS + 40),
    );
  }

  async function onLogin(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(errorKey(err));
      setPassword("");
      setBusy(false);
    }
  }

  async function onRegister(e: FormEvent) {
    e.preventDefault();
    if (regBusy) return;
    setRegError(null);
    if (regPw !== regPw2) {
      setRegError("auth.mismatch");
      return;
    }
    setRegBusy(true);
    try {
      await api("/auth/register/", {
        method: "POST",
        skipRefresh: true,
        body: JSON.stringify({
          email: regEmail.trim(),
          password: regPw,
          display_name: regName.trim(),
          preferred_language: lang,
        }),
      });
      setEmail(regEmail.trim());
      setPassword("");
      setRegName("");
      setRegEmail("");
      setRegPw("");
      setRegPw2("");
      setRegBusy(false);
      switchTo("login");
      setNotice({ kind: "ok", key: "auth.registered" });
    } catch (err) {
      setRegError(registerErrorKey(err));
      setRegPw("");
      setRegPw2("");
      setRegBusy(false);
    }
  }

  const socialSoon = () => setNotice({ kind: "info", key: "auth.socialSoon" });
  const forgot = () => setNotice({ kind: "info", key: "auth.forgotInfo" });

  const noticeEl = notice && (
    <p className={`auth-msg ${notice.kind}`} role="status">{t(notice.key)}</p>
  );

  return (
    <div className="auth-page">
      <header className="auth-top"><LanguageToggle /></header>

      <main className="auth-main">
        <div className="auth-card2" data-view={view} data-anim={anim ?? undefined}>
          <div className="auth-logo2" data-tone={tone}>
            <span className="mark" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 14l5-5 4 4 8-8" />
              </svg>
            </span>
            <span>
              <span className="a">Predict</span>
              <span className="b">Rx</span>
            </span>
          </div>

          {/* ---------- Registration (left) ---------- */}
          <section
            className="auth-pane auth-pane--register"
            aria-labelledby="reg-title"
            {...inertIf(view !== "register")}
          >
            <form className="auth-form" onSubmit={onRegister}>
              <h1 id="reg-title" className="auth-title">{t("auth.registration")}</h1>

              <div className="auth-input">
                <input
                  type="text" value={regName} onChange={(e) => setRegName(e.target.value)}
                  placeholder={t("auth.username")} aria-label={t("auth.username")}
                  autoComplete="name" maxLength={150} required
                />
                <UserIcon />
              </div>
              <div className="auth-input">
                <input
                  type="email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)}
                  placeholder={t("login.email")} aria-label={t("login.email")}
                  autoComplete="email" inputMode="email" required
                />
                <MailIcon />
              </div>
              <div className="auth-input has-eye">
                <input
                  type={showRegPw ? "text" : "password"} value={regPw} onChange={(e) => setRegPw(e.target.value)}
                  placeholder={t("login.password")} aria-label={t("login.password")}
                  autoComplete="new-password" minLength={8} required
                />
                <EyeButton shown={showRegPw} onToggle={() => setShowRegPw((v) => !v)} label={t(showRegPw ? "login.hide" : "login.show")} />
                <LockIcon />
              </div>
              <div className="auth-input">
                <input
                  type={showRegPw ? "text" : "password"} value={regPw2} onChange={(e) => setRegPw2(e.target.value)}
                  placeholder={t("auth.confirmPassword")} aria-label={t("auth.confirmPassword")}
                  autoComplete="new-password" minLength={8} required
                />
                <LockIcon />
              </div>

              {regError && <p className="auth-msg err" role="alert">{t(regError)}</p>}
              {view === "register" && noticeEl}

              <button type="submit" className="auth-submit" disabled={regBusy}>
                {t(regBusy ? "auth.registering" : "auth.register")}
              </button>

              <p className="auth-or">{t("auth.orRegisterSocial")}</p>
              <SocialRow onClick={socialSoon} />
            </form>
          </section>

          {/* ---------- Login (right) ---------- */}
          <section
            className="auth-pane auth-pane--login"
            aria-labelledby="login-title"
            {...inertIf(view !== "login")}
          >
            <form className="auth-form" onSubmit={onLogin}>
              <h1 id="login-title" className="auth-title">{t("auth.login")}</h1>

              <div className="auth-input">
                <input
                  type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder={t("login.email")} aria-label={t("login.email")}
                  autoComplete="username" inputMode="email" required
                />
                <UserIcon />
              </div>
              <div className="auth-input has-eye">
                <input
                  type={showPw ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder={t("login.password")} aria-label={t("login.password")}
                  autoComplete="current-password" required
                />
                <EyeButton shown={showPw} onToggle={() => setShowPw((v) => !v)} label={t(showPw ? "login.hide" : "login.show")} />
                <LockIcon />
              </div>

              <button type="button" className="auth-forgot" onClick={forgot}>{t("auth.forgot")}</button>

              {error && <p className="auth-msg err" role="alert">{t(error)}</p>}
              {view === "login" && noticeEl}

              <button type="submit" className="auth-submit" disabled={busy}>
                {t(busy ? "login.submitting" : "auth.login")}
              </button>

              <p className="auth-or">{t("auth.orLoginSocial")}</p>
              <SocialRow onClick={socialSoon} />
            </form>
          </section>

          {/* ---------- Sliding teal panel ---------- */}
          <div className="auth-panel">
            <div className="auth-block auth-block--reg" {...inertIf(view !== "register")}>
              <h2>{t("auth.welcomeBack")}</h2>
              <p>{t("auth.haveAccount")}</p>
              <button type="button" className="auth-ghost" onClick={() => switchTo("login")} disabled={anim !== null}>
                {t("auth.login")}
              </button>
            </div>
            <div className="auth-block auth-block--login" {...inertIf(view !== "login")}>
              <h2>{t("auth.hello")}</h2>
              <p>{t("auth.noAccount")}</p>
              <button type="button" className="auth-ghost" onClick={() => switchTo("register")} disabled={anim !== null}>
                {t("auth.register")}
              </button>
            </div>
          </div>
        </div>
      </main>

      <DisclaimerStrip />
    </div>
  );
}

function SocialRow({ onClick }: { onClick: () => void }) {
  return (
    <div className="auth-social">
      <button type="button" onClick={onClick} aria-label="Google">G</button>
      <button type="button" onClick={onClick} aria-label="Facebook">f</button>
      <button type="button" onClick={onClick} aria-label="LinkedIn">in</button>
    </div>
  );
}

function EyeButton({ shown, onToggle, label }: { shown: boolean; onToggle: () => void; label: string }) {
  return (
    <button type="button" className="pw-eye" onClick={onToggle} aria-pressed={shown} aria-label={label}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" />
        <circle cx="12" cy="12" r="3" />
        {shown && <path d="M3 3l18 18" />}
      </svg>
    </button>
  );
}

function UserIcon() {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <circle cx="12" cy="7.5" r="4.5" />
      <path d="M3 21c0-4.4 4-7 9-7s9 2.6 9 7z" />
    </svg>
  );
}
function MailIcon() {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M2 5h20v14H2z" />
      <path d="M2.5 5.5L12 13l9.5-7.5" fill="none" stroke="#eeeae7" strokeWidth="1.8" />
    </svg>
  );
}
function LockIcon() {
  return (
    <svg className="ico" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="4" y="10" width="16" height="12" rx="2" />
      <path d="M7.5 10V7a4.5 4.5 0 019 0v3" fill="none" stroke="currentColor" strokeWidth="2.4" />
    </svg>
  );
}