import type { ApiError } from "./types";

const BASE = import.meta.env.VITE_API_URL ?? "/api";

// Tokens live in memory only (not localStorage). TODO: move to httpOnly cookies when the backend supports it.
let accessToken: string | null = null;
let refreshToken: string | null = null;

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access;
  refreshToken = refresh;
}
export const isLoggedIn = () => accessToken !== null;
export const getRefreshToken = () => refreshToken;

export class ApiRequestError extends Error {
  constructor(public status: number, public body: ApiError | null) {
    super(body?.error?.message ?? `Request failed (${status})`);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
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

export async function login(email: string, password: string) {
  const data = await api<{ access: string; refresh: string }>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setTokens(data.access, data.refresh);
}
