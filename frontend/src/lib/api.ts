import type { ApiError, User } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

// The short-lived access token lives in memory only (rule.md §5: never localStorage). The long-lived refresh token is
// an httpOnly cookie set by the server: JavaScript never sees it, and it is what keeps you signed in after a reload
// (see restoreSession). `credentials: "include"` makes the browser send that cookie even if VITE_API_URL is another origin.
let accessToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export function setTokens(access: string | null) {
  accessToken = access;
}
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
  refreshing ??= (async () => {
    try {
      // No token in the body: the server reads the httpOnly cookie and rotates it.
      const res = await fetch(`${BASE}/auth/token/refresh/`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!res.ok) return false;
      const data = (await res.json()) as { access: string };
      setTokens(data.access);
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
    res = await fetch(`${BASE}${path}`, { credentials: "include", ...init, headers });
  } catch {
    throw new ApiRequestError(0, null);
  }

  if (res.status === 401 && !skipRefresh) {
    if (await refreshAccess()) return api<T>(path, { ...init, skipRefresh: true }); // retry once, new token
    setTokens(null);
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

interface BlobOptions {
  signal?: AbortSignal;
  skipRefresh?: boolean;
}

/**
 * GET a binary body (the prescription image). An <img src> cannot send the Authorization header and the server has
 * deliberately no public image URL, so the image is fetched here and shown from a blob URL (backend ScanImageView).
 * Same auth, same single refresh-and-retry and same error type as api().
 */
export async function apiBlob(path: string, { signal, skipRefresh }: BlobOptions = {}): Promise<Blob> {
  const headers = new Headers();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { headers, signal, cache: "no-store" });
  } catch {
    throw new ApiRequestError(0, null);
  }

  if (res.status === 401 && !skipRefresh) {
    if (await refreshAccess()) return apiBlob(path, { signal, skipRefresh: true });
    setTokens(null);
    onSessionExpired?.();
  }

  if (!res.ok) {
    let body: ApiError | null = null;
    try {
      body = (await res.json()) as ApiError;
    } catch {
      /* the image endpoint answers errors as JSON; anything else is treated as a plain failure */
    }
    throw new ApiRequestError(res.status, body);
  }
  return res.blob();
}

export async function login(email: string, password: string): Promise<User> {
  // The response also carries the refresh token in development; it is ignored on purpose: the cookie is what counts.
  const data = await api<{ access: string }>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipRefresh: true,
  });
  setTokens(data.access);
  return api<User>("/auth/me/");
}

/** Called once when the app starts: if the httpOnly session cookie is still valid, sign the user in again. */
export async function restoreSession(): Promise<User | null> {
  try {
    if (!(await refreshAccess())) return null;
    return await api<User>("/auth/me/", { skipRefresh: true });
  } catch {
    setTokens(null);
    return null;
  }
}

export async function logout(): Promise<void> {
  try {
    // The server blacklists the refresh token from the cookie and clears it.
    await api("/auth/logout/", { method: "POST", body: "{}", skipRefresh: true });
  } catch {
    /* the server-side blacklist is best effort; we still drop the access token locally */
  } finally {
    setTokens(null);
  }
}
