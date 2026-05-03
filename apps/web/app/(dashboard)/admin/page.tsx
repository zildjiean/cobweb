"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Building2,
  History as HistoryIcon,
  KeyRound,
  Mail,
  Shield,
  ShieldCheck,
  Sparkles,
  User,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader, Skeleton } from "@/components/ui/EmptyState";

interface Me {
  email: string;
  full_name: string;
  role: string | null;
  org_id: string | null;
  org_name: string | null;
  mfa_enabled: boolean;
}

export default function AdminPage() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Me>("/api/v1/auth/me"),
  });

  return (
    <div>
      <PageHeader
        title="Admin"
        description="Account and organization configuration."
      />

      {me.error && (
        <p className="text-severity-critical">
          {me.error instanceof ApiError ? me.error.message : "Error"}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <div className="card md:col-span-2">
          <h2 className="section-title mb-3">Account</h2>
          {me.isLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <dl className="grid gap-y-2.5 text-sm md:grid-cols-[200px_1fr]">
              <DT icon={User} label="Name" />
              <dd className="text-slate-100">
                {me.data?.full_name || (
                  <span className="italic text-slate-500">—</span>
                )}
              </dd>
              <DT icon={Mail} label="Email" />
              <dd className="font-mono text-xs">{me.data?.email}</dd>
              <DT icon={Shield} label="Role" />
              <dd>
                <span className="badge bg-accent/15 text-accent">
                  {me.data?.role ?? "none"}
                </span>
              </dd>
              <DT icon={Building2} label="Organization" />
              <dd>
                <div className="text-slate-100">
                  {me.data?.org_name || "—"}
                </div>
                <div className="font-mono text-[11px] text-slate-500">
                  {me.data?.org_id || "—"}
                </div>
              </dd>
              <DT icon={ShieldCheck} label="MFA" />
              <dd>
                {me.data?.mfa_enabled ? (
                  <span className="badge bg-emerald-500/15 text-emerald-300">
                    Enabled
                  </span>
                ) : (
                  <span className="badge bg-amber-500/15 text-amber-300">
                    Not enabled
                  </span>
                )}
              </dd>
            </dl>
          )}
        </div>

        <div className="space-y-3">
          <Link
            href="/integrations"
            className="card card-hover block"
          >
            <div className="mb-1.5 flex h-8 w-8 items-center justify-center rounded-md bg-accent/15 text-accent">
              <KeyRound className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold">API tokens</h3>
            <p className="text-[11px] text-slate-400">
              Manage CI/CD API keys and integrations
            </p>
          </Link>
          <Link
            href="/audit"
            className="card card-hover block"
          >
            <div className="mb-1.5 flex h-8 w-8 items-center justify-center rounded-md bg-purple-500/15 text-purple-300">
              <HistoryIcon className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold">Audit log</h3>
            <p className="text-[11px] text-slate-400">
              Hash-chained activity timeline
            </p>
          </Link>
          <Link
            href="/admin/llm"
            className="card card-hover block"
          >
            <div className="mb-1.5 flex h-8 w-8 items-center justify-center rounded-md bg-emerald-500/15 text-emerald-300">
              <Sparkles className="h-4 w-4" />
            </div>
            <h3 className="text-sm font-semibold">LLM translation</h3>
            <p className="text-[11px] text-slate-400">
              Provider, model, and Thai translation prompt
            </p>
          </Link>
        </div>
      </div>

      <div className="card mt-4">
        <h2 className="section-title mb-3">Coming soon</h2>
        <ul className="grid gap-2 text-sm text-slate-300 md:grid-cols-2">
          <li className="flex items-center gap-2 rounded-md bg-bg/40 px-3 py-2">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
            User invitation + role management
          </li>
          <li className="flex items-center gap-2 rounded-md bg-bg/40 px-3 py-2">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
            SSO configuration (OIDC / SAML)
          </li>
          <li className="flex items-center gap-2 rounded-md bg-bg/40 px-3 py-2">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
            SLA policy per severity
          </li>
          <li className="flex items-center gap-2 rounded-md bg-bg/40 px-3 py-2">
            <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
            Organization billing / quota
          </li>
        </ul>
      </div>
    </div>
  );
}

function DT({
  icon: Icon,
  label,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <dt className="flex items-center gap-2 text-xs text-slate-400">
      <Icon className="h-3.5 w-3.5" />
      {label}
    </dt>
  );
}
