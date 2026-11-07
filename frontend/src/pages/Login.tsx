import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useI18n } from "../i18n";
import { login } from "../lib/api";

export default function Login() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFailed(false);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h1>{t("login.title")}</h1>
      <form onSubmit={onSubmit}>
        <label className="field">
          {t("login.email")}
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        </label>
        <label className="field">
          {t("login.password")}
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {failed && <p className="error" role="alert">{t("login.failed")}</p>}
        <button type="submit" className="btn" disabled={busy}>{t("login.submit")}</button>
      </form>
    </section>
  );
}
