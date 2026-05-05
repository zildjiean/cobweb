"use client";

// Resolve at request time so that:
//   - if NEXT_PUBLIC_API_BASE is set at build time, that wins (explicit deploy);
//   - otherwise, in the browser, default to the same hostname that served the
//     web app on port 8000. Lets the dev box answer on multiple IPs / NAT
//     paths (e.g. 192.168.0.144 and 10.6.1.52) without rebuilds.
//   - on the server (SSR / build), fall back to localhost.
const ENV_API_BASE = process.env.NEXT_PUBLIC_API_BASE;

function resolveApiBase(): string {
  if (ENV_API_BASE) return ENV_API_BASE;
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

export function wsUrl(path: string): string {
  const u = new URL(resolveApiBase());
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = path;
  return u.toString();
}

const TOKEN_KEY = "cobweb.access_token";

export const tokenStore = {
  get: (): string | null =>
    typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY),
  set: (token: string) => window.localStorage.setItem(TOKEN_KEY, token),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

export async function api<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("authorization", `Bearer ${token}`);

  const r = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!r.ok) {
    let body: unknown;
    try { body = await r.json(); } catch { /* ignore */ }
    const detail =
      (body as { detail?: string } | undefined)?.detail ?? r.statusText;
    throw new ApiError(r.status, detail, body);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}
