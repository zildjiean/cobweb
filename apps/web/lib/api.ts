"use client";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export function wsUrl(path: string): string {
  const u = new URL(API_BASE);
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
