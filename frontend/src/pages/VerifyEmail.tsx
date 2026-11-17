import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { DisclaimerStrip } from "../components/ui/DisclaimerStrip";
import { LanguageToggle } from "../components/ui/LanguageToggle";
import { useI18n } from "../i18n";
import { api } from "../lib/api";
import "../styles/auth.css";

/** Route: /verify-email?token=… (public). Opened from the link in the verification email. */
export default function VerifyEmail() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"working" | "ok" | "error">(token ? "working" : "error");

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
