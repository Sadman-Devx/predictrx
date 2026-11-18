import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusPill } from "../components/ui/StatusPill";
import { useI18n, type MessageKey } from "../i18n";
import { api, ApiRequestError } from "../lib/api";
import { reasonsOf } from "../lib/errors";
import type { User } from "../lib/types";
import "../styles/profile.css";

type Status = { kind: "ok" | "error"; text: string } | null;

/** Route: /profile (every signed-in role). Account details, display name, resend verification, change password. */
export default function Profile() {
  const { t } = useI18n();
  const { user, logout, updateUser } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState(user?.display_name ?? "");
  const [nameBusy, setNameBusy] = useState(false);
  const [nameStatus, setNameStatus] = useState<Status>(null);

  const [verifyStatus, setVerifyStatus] = useState<Status>(null);

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwStatus, setPwStatus] = useState<Status>(null);
  const [changed, setChanged] = useState(false);

  if (!user) return null; // ProtectedRoute already guarantees a user

  async function saveName(e: FormEvent) {
    e.preventDefault();
    if (nameBusy) return;
    setNameBusy(true);
    setNameStatus(null);
    try {
      const me = await api<User>("/auth/me/", { method: "PATCH", body: JSON.stringify({ display_name: name.trim() }) });
      updateUser(me);
      setNameStatus({ kind: "ok", text: t("profile.saved") });
    } catch {
      setNameStatus({ kind: "error", text: t("profile.saveError") });
    } finally {
      setNameBusy(false);
    }
  }

  async function resendVerification() {
    setVerifyStatus(null);
    try {
      const email = user!.email;
      await api("/auth/resend-verification/", { method: "POST", body: JSON.stringify({ email }) });
      navigate(`/verify-email?email=${encodeURIComponent(email)}`, {
        state: { resendRequested: true },
      });
    } catch (err) {
      setVerifyStatus({ kind: "error", text: failureText(err) });
    }
  }

  function failureText(err: unknown, fallback: MessageKey = "login.server"): string {
    if (err instanceof ApiRequestError) {
      if (err.status === 0) return t("login.network");
      if (err.status === 429) return t("login.tooMany");
      if (err.status >= 500) return t("login.server");
      const reasons = reasonsOf(err);
      if (reasons.length) return reasons.join(" ");
    }
    return t(fallback);
  }

  async function changePassword(e: FormEvent) {
    e.preventDefault();
    if (pwBusy) return;
    if (next !== confirm) {
      setPwStatus({ kind: "error", text: t("auth.mismatch") });
      return;
    }
    setPwBusy(true);
    setPwStatus(null);
    try {
      await api("/auth/change-password/", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      setChanged(true); // every refresh token is dead now: the form is replaced by "log in again"
      setPwStatus({ kind: "ok", text: t("profile.password.changed") });
    } catch (err) {
      setPwStatus({ kind: "error", text: failureText(err, "profile.password.error") });
    } finally {
      setPwBusy(false);
    }
  }

  async function loginAgain() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <section className="profile">
      <PageHeader title={t("profile.title")} />

      <div className="card profile-card">
        <h2 className="profile-h">{t("profile.account")}</h2>
        <dl className="profile-facts">
          <div><dt>{t("profile.email")}</dt><dd>{user.email}</dd></div>
          <div><dt>{t("profile.role")}</dt><dd>{t(`profile.role.${user.role}` as MessageKey)}</dd></div>
          <div>
            <dt>{t("profile.verified")}</dt>
            <dd>
              <StatusPill tone={user.email_verified ? "ok" : "warn"}>
                {t(user.email_verified ? "profile.verified" : "profile.notVerified")}
              </StatusPill>
            </dd>
          </div>
        </dl>
        {user.email_verified === false && (
          <div className="profile-row">
            <button type="button" className="btn secondary" onClick={() => void resendVerification()}>
              {t("profile.resend")}
            </button>
          </div>
        )}
        {verifyStatus && <p className={`profile-msg ${verifyStatus.kind}`} role="status">{verifyStatus.text}</p>}
      </div>

      <form className="card profile-card" onSubmit={saveName}>
        <h2 className="profile-h">{t("profile.details")}</h2>
        <label className="profile-field">
          <span>{t("profile.name")}</span>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} maxLength={150} autoComplete="name" />
        </label>
        <div className="profile-row">
          <button type="submit" className="btn" disabled={nameBusy}>{t(nameBusy ? "profile.saving" : "profile.save")}</button>
        </div>
        {nameStatus && <p className={`profile-msg ${nameStatus.kind}`} role="status">{nameStatus.text}</p>}
      </form>

      <form className="card profile-card" onSubmit={changePassword}>
        <h2 className="profile-h">{t("profile.password.title")}</h2>
        {changed ? (
          <>
            {pwStatus && <p className={`profile-msg ${pwStatus.kind}`} role="status">{pwStatus.text}</p>}
            <div className="profile-row">
              <button type="button" className="btn" onClick={() => void loginAgain()}>{t("profile.password.relogin")}</button>
            </div>
          </>
        ) : (
          <>
            <p className="muted small">{t("profile.password.hint")}</p>
            <label className="profile-field">
              <span>{t("profile.password.current")}</span>
              <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
            </label>
            <label className="profile-field">
              <span>{t("profile.password.new")}</span>
              <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={8} required />
            </label>
            <label className="profile-field">
              <span>{t("profile.password.confirm")}</span>
              <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" minLength={8} required />
            </label>
            <div className="profile-row">
              <button type="submit" className="btn" disabled={pwBusy}>
                {t(pwBusy ? "profile.password.submitting" : "profile.password.submit")}
              </button>
            </div>
            {pwStatus && <p className={`profile-msg ${pwStatus.kind}`} role="alert">{pwStatus.text}</p>}
          </>
        )}
      </form>
    </section>
  );
}
