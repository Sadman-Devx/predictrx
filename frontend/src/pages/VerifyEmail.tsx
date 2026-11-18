import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { DisclaimerStrip } from "../components/ui/DisclaimerStrip";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useI18n, type MessageKey } from "../i18n";
import { api, ApiRequestError } from "../lib/api";
import "../styles/auth.css";

/** Public route for six-digit OTP verification and older signed verification links. */
export default function VerifyEmail() {
  const { t } = useI18n();
  const location = useLocation();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"working" | "ok" | "error" | "entry">(token ? "working" : "entry");
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState<MessageKey | null>(() => {
    const navState = location.state as { emailSent?: boolean; resendRequested?: boolean } | null;
    if (navState?.emailSent === false) return "verify.sendFailed";
    if (navState?.resendRequested) return "verify.resendSent";
    return null;
  });
  const [resendUntil, setResendUntil] = useState(() => {
    const navState = location.state as { emailSent?: boolean; resendRequested?: boolean } | null;
    return navState?.emailSent || navState?.resendRequested ? Date.now() + 60_000 : 0;
  });
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!resendUntil) {
      setSecondsLeft(0);
      return;
    }
    const update = () => setSecondsLeft(Math.max(0, Math.ceil((resendUntil - Date.now()) / 1000)));
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [resendUntil]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api("/auth/verify-email/", { method: "POST", skipRefresh: true, body: JSON.stringify({ token }) })
      .then(() => !cancelled && setState("ok"))
      .catch(() => !cancelled && setState("error")); // opening the link twice is fine on the server side
    return () => {
      cancelled = true;
    };
  }, [token]);

  function failureMessage(err: unknown): MessageKey {
    if (err instanceof ApiRequestError) {
    if (err.status === 0) return "login.network";
    if (err.status === 429) return "login.tooMany";
    if (err.status >= 500) return "login.server";
    }
    return "verify.failed";
  }

  async function verifyCode(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
    await api("/auth/verify-email/", {
      method: "POST",
      skipRefresh: true,
      body: JSON.stringify({ email: email.trim(), code }),
    });
    setState("ok");
    } catch (err) {
    setError(failureMessage(err));
    } finally {
    setBusy(false);
    }
  }

  async function resendCode() {
    if (busy || secondsLeft > 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
    await api("/auth/resend-verification/", {
      method: "POST",
      skipRefresh: true,
      body: JSON.stringify({ email: email.trim() }),
    });
    setCode("");
    setNotice("verify.resendSent");
    setResendUntil(Date.now() + 60_000);
    } catch (err) {
    setError(failureMessage(err));
    } finally {
    setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <header className="auth-top"><LanguageToggle /></header>
      <main className="auth-main">
        <section className="reset-card" aria-labelledby="verify-title">
          <div className="auth-form">
            <h1 id="verify-title" className="auth-title">{t("verify.title")}</h1>
            {state === "working" && <p className="reset-description" role="status" aria-busy="true">{t("verify.working")}</p>}
            {state === "ok" && <p className="auth-msg ok" role="status">{t("verify.ok")}</p>}
            {state === "error" && <p className="auth-msg err" role="alert">{t("verify.failed")}</p>}
            {state === "entry" && (
              <form className="auth-form otp-form" onSubmit={verifyCode}>
                <p className="reset-description">{t("verify.instructions")}</p>
                {notice && <p className="auth-msg info" role="status">{t(notice)}</p>}
                {error && <p className="auth-msg err" role="alert">{t(error)}</p>}
                <label className="otp-label" htmlFor="verification-email">{t("login.email")}</label>
                <div className="auth-input">
                  <input
                    id="verification-email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    autoComplete="email"
                    inputMode="email"
                    required
                  />
                </div>
                <label className="otp-label" htmlFor="verification-code">{t("verify.code")}</label>
                <div className="auth-input otp-input">
                  <input
                    id="verification-code"
                    type="text"
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    required
                  />
                </div>
                <button type="submit" className="auth-submit" disabled={busy || code.length !== 6}>
                  {t(busy ? "verify.submitting" : "verify.submit")}
                </button>
                <button
                  type="button"
                  className="auth-resend"
                  onClick={() => void resendCode()}
                  disabled={busy || secondsLeft > 0 || !email.trim()}
                >
                  {secondsLeft > 0 ? t("verify.resendWait", { seconds: secondsLeft }) : t("verify.resend")}
                </button>
              </form>
            )}
            <Link to="/login" className="auth-submit" style={{ textAlign: "center", textDecoration: "none" }}>
              {t("verify.toLogin")}
            </Link>
          </div>
        </section>
      </main>
      <DisclaimerStrip />
    </div>
  );
}
