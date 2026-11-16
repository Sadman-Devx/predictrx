import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DisclaimerStrip } from "../components/ui/DisclaimerStrip";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useI18n, type MessageKey } from "../i18n";
import { api, ApiRequestError } from "../lib/api";
import "../styles/auth.css";

type Status = { kind: "ok" | "error"; text: string } | null;

function collectReasons(details: unknown): string[] {
  if (typeof details === "string") return [details];
  if (Array.isArray(details)) return details.flatMap(collectReasons);
  if (details && typeof details === "object") return Object.values(details).flatMap(collectReasons);
  return [];
}

export default function ResetPassword() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";
  const hasLink = Boolean(uid || token);
  const validLink = Boolean(uid && token);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  function failureText(error: unknown): string {
    if (error instanceof ApiRequestError) {
      if (error.status === 0) return t("login.network");
      if (error.status === 429) return t("login.tooMany");
      if (error.status >= 500) return t("login.server");
      const reasons = [...new Set(collectReasons(error.body?.error?.details))];
      if (reasons.length) return reasons.join(" ");
    }
    return t("reset.error");
  }

  async function requestReset(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setStatus(null);
    try {
      await api("/auth/password-reset/", {
        method: "POST",
        skipRefresh: true,
        body: JSON.stringify({ email: email.trim() }),
      });
      setStatus({ kind: "ok", text: t("reset.requestSent") });
    } catch (error) {
      setStatus({ kind: "error", text: failureText(error) });
    } finally {
      setBusy(false);
    }
  }

  async function confirmReset(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (password !== confirm) {
      setStatus({ kind: "error", text: t("auth.mismatch") });
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      await api("/auth/password-reset/confirm/", {
        method: "POST",
        skipRefresh: true,
        body: JSON.stringify({ uid, token, password }),
      });
      setStatus({ kind: "ok", text: t("reset.changed") });
      setPassword("");
      setConfirm("");
    } catch (error) {
      setStatus({ kind: "error", text: failureText(error) });
    } finally {
      setBusy(false);
    }
  }

  const titleKey: MessageKey = validLink ? "reset.newTitle" : "reset.title";

  return (
    <div className="auth-page">
      <header className="auth-top"><LanguageToggle /></header>
      <main className="auth-main">
        <section className="reset-card" aria-labelledby="reset-title">
          <form className="auth-form" onSubmit={validLink ? confirmReset : requestReset}>
            <h1 id="reset-title" className="auth-title">{t(titleKey)}</h1>
            <p className="reset-description">{t(validLink ? "reset.newHint" : "reset.hint")}</p>

            {hasLink && !validLink ? (
              <p className="auth-msg err" role="alert">{t("reset.invalidLink")}</p>
            ) : validLink ? (
              <>
                <div className="auth-input">
                  <input
                    type="password" value={password} onChange={(event) => setPassword(event.target.value)}
                    placeholder={t("reset.newPassword")} aria-label={t("reset.newPassword")}
                    autoComplete="new-password" minLength={8} required
                  />
                </div>
                <div className="auth-input">
                  <input
                    type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)}
                    placeholder={t("auth.confirmPassword")} aria-label={t("auth.confirmPassword")}
                    autoComplete="new-password" minLength={8} required
                  />
                </div>
              </>
            ) : (
              <div className="auth-input">
                <input
                  type="email" value={email} onChange={(event) => setEmail(event.target.value)}
                  placeholder={t("login.email")} aria-label={t("login.email")}
                  autoComplete="email" inputMode="email" required
                />
              </div>
            )}

            {status && <p className={`auth-msg ${status.kind}`} role={status.kind === "error" ? "alert" : "status"}>{status.text}</p>}

            {(!hasLink || validLink) && (
              <button type="submit" className="auth-submit" disabled={busy}>
                {t(busy ? "reset.submitting" : validLink ? "reset.changeButton" : "reset.requestButton")}
              </button>
            )}
            {hasLink && !validLink && (
              <Link className="auth-forgot reset-link" to="/reset-password">{t("reset.requestAnother")}</Link>
            )}
            <Link className="auth-forgot reset-link" to="/login">{t("reset.backToLogin")}</Link>
          </form>
        </section>
      </main>
      <DisclaimerStrip />
    </div>
  );
}
