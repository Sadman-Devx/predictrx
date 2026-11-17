import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useI18n } from "../i18n";
import { login as apiLogin, logout as apiLogout, restoreSession, setSessionExpiredHandler } from "../lib/api";
import type { User } from "../lib/types";

interface AuthValue {
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Replace the signed-in user after the profile was edited. */
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { t, setLang } = useI18n();
  const [user, setUser] = useState<User | null>(null);
  // false until we know whether the httpOnly session cookie still gives us a signed-in user (page reload).
  const [ready, setReady] = useState(false);

  // api.ts calls this when a refresh fails -> send the user back to login.
  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null));
    return () => setSessionExpiredHandler(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void restoreSession().then((me) => {
      if (cancelled) return;
      if (me) {
        setUser(me);
        if (me.preferred_language === "bn" || me.preferred_language === "en") setLang(me.preferred_language);
      }
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once at start-up
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const me = await apiLogin(email, password);
      setUser(me);
      if (me.preferred_language === "bn" || me.preferred_language === "en") setLang(me.preferred_language);
    },
    [setLang],
  );

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, login, logout, updateUser: setUser }), [user, login, logout]);

  // Do not flash the login page for a signed-in person while the cookie is being checked.
  if (!ready) return <div className="boot" role="status" aria-busy="true">{t("common.loading")}</div>;
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
