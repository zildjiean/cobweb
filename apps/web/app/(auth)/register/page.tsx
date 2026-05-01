"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { ApiError, api, tokenStore } from "@/lib/api";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  requires_mfa: boolean;
}

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api<TokenResponse>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          full_name: fullName,
          org_name: orgName,
        }),
      });
      tokenStore.set(res.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden p-6">
      <div
        aria-hidden
        className="absolute left-1/2 top-1/2 h-[420px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-purple-500/15 blur-3xl"
      />

      <div className="relative w-full max-w-sm">
        <div className="mb-6 text-center">
          <Link href="/" className="inline-flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-accent-subtle text-base font-bold text-white shadow-glow">
              C
            </div>
            <span className="text-xl font-semibold tracking-tight">
              Cob<span className="text-accent">web</span>
            </span>
          </Link>
          <p className="mt-3 text-sm text-slate-400">
            Create your organization
          </p>
        </div>

        <form onSubmit={onSubmit} className="card space-y-4 animate-fade-in">
          <div>
            <label className="label" htmlFor="org">Organization name</label>
            <input
              id="org"
              required
              placeholder="Acme Corp"
              className="input"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <label className="label" htmlFor="full">Your name</label>
            <input
              id="full"
              required
              placeholder="Jane Doe"
              className="input"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="email">Work email</label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              placeholder="you@company.com"
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              required
              autoComplete="new-password"
              minLength={12}
              placeholder="at least 12 characters"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="mt-1 text-[11px] text-slate-500">
              Must be at least 12 characters.
            </p>
          </div>
          {error && (
            <div className="flex items-start gap-2 rounded-md border border-severity-critical/40 bg-severity-critical/10 p-2.5 text-xs text-severity-critical">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <button type="submit" disabled={busy} className="btn-primary w-full">
            {busy ? "Creating…" : "Create organization"}
          </button>
          <div className="text-center text-xs text-slate-500">
            Already have an account?{" "}
            <Link href="/login" className="text-accent hover:underline">
              Sign in
            </Link>
          </div>
        </form>
      </div>
    </main>
  );
}
