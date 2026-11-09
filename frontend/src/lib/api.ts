import type { ApiError, User } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

// Tokens live in memory only (rule.md §5: never localStorage). A page reload therefore logs the user out.
// TODO: move to httpOnly cookies when the backend supports it.
let accessToken: string | null = null;
let refreshToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access;
  refreshToken = refresh;
}
export const getRefreshToken = () => refreshToken;
export function setSessionExpiredHandler(fn: (() => void) | null) {
  onSessionExpired = fn;
}

/** status 0 = the request never reached the server (offline, DNS, CORS). */
export class ApiRequestError extends Error {
  constructor(public status: number, public body: ApiError | null) {
    super(body?.error?.message ?? (status === 0 ? "Network error" : `Request failed (${status})`));
  }
}

// One refresh at a time: if 3 requests get 401 together they share a single refresh call
// (refresh tokens rotate and are blacklisted, so parallel refreshes would invalidate each other).
let refreshing: Promise<boolean> | null = null;
function refreshAccess(): Promise<boolean> {
  if (!refreshToken) return Promise.resolve(false);
  refreshing ??= (async () => {
    try {
      const res = await fetch(`${BASE}/auth/token/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: refreshToken }),
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { access: string; refresh?: string };
      setTokens(data.access, data.refresh ?? refreshToken);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

interface Options extends RequestInit {
  /** Don't try refresh-and-retry on 401 (used by login itself). */
  skipRefresh?: boolean;
}

export async function api<T>(path: string, { skipRefresh, ...init }: Options = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiRequestError(0, null);
  }

  if (res.status === 401 && !skipRefresh && refreshToken) {
    if (await refreshAccess()) return api<T>(path, { ...init, skipRefresh: true }); // retry once, new token
    setTokens(null, null);
    onSessionExpired?.();
  }

  if (!res.ok) {
    let body: ApiError | null = null;
    try {
      body = (await res.json()) as ApiError;
    } catch {
      /* non-JSON error */
    }
    throw new ApiRequestError(res.status, body);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export async function login(email: string, password: string): Promise<User> {
  const data = await api<{ access: string; refresh: string }>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipRefresh: true,
  });
  setTokens(data.access, data.refresh);
  return api<User>("/auth/me/");
}

export async function logout(): Promise<void> {
  const refresh = refreshToken;
  try {
    if (refresh) await api("/auth/logout/", { method: "POST", body: JSON.stringify({ refresh }), skipRefresh: true });
  } catch {
    /* server-side blacklist is best effort; we still drop the tokens locally */
  } finally {
    setTokens(null, null);
  }
}