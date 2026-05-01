"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Bell,
  Bug as BugIcon,
  Check,
  Copy,
  Key,
  Plus,
  Webhook,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

interface Token {
  id: string;
  name: string;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

interface CreateResp extends Token {
  plaintext: string;
}

export default function IntegrationsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [justCreated, setJustCreated] = useState<CreateResp | null>(null);
  const [copied, setCopied] = useState(false);
  const [pendingRevoke, setPendingRevoke] = useState<Token | null>(null);

  const tokens = useQuery({
    queryKey: ["tokens"],
    queryFn: () => api<Token[]>("/api/v1/tokens"),
  });

  const create = useMutation({
    mutationFn: (n: string) =>
      api<CreateResp>("/api/v1/tokens", {
        method: "POST",
        body: JSON.stringify({ name: n }),
      }),
    onSuccess: (resp) => {
      setJustCreated(resp);
      setName("");
      qc.invalidateQueries({ queryKey: ["tokens"] });
      toast.push({
        kind: "success",
        title: "Token created",
        description: "Copy the plaintext key now — it won't be shown again.",
      });
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Failed to create token",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  const revoke = useMutation({
    mutationFn: (id: string) =>
      api(`/api/v1/tokens/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tokens"] });
      toast.push({ kind: "success", title: "Token revoked" });
    },
  });

  const onCopyKey = () => {
    if (!justCreated) return;
    navigator.clipboard?.writeText(justCreated.plaintext);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Integrations"
        description="API tokens for CI/CD, plus notification & issue tracker channels."
      />

      <section className="card">
        <div className="mb-3 flex items-center gap-2">
          <Key className="h-4 w-4 text-accent" />
          <h2 className="text-sm font-semibold">API tokens (CI/CD)</h2>
        </div>
        <p className="mb-3 text-xs text-slate-400">
          Use with the <code className="text-accent">cobweb-cli</code> or
          <code className="ml-1 text-accent">X-Api-Key</code> header. The full
          key is shown <strong>only once</strong> on creation — copy it now.
        </p>

        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name) create.mutate(name);
          }}
        >
          <label className="flex-1 min-w-[200px]">
            <span className="label">Token name</span>
            <input
              className="input"
              placeholder="github-actions-prod"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>
          <button className="btn-primary" disabled={create.isPending}>
            <Plus className="h-4 w-4" />
            {create.isPending ? "Creating…" : "Create token"}
          </button>
        </form>

        {justCreated && (
          <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 animate-fade-in">
            <p className="text-xs text-amber-200">
              <strong>{justCreated.name}</strong> — copy now, this is the only
              chance:
            </p>
            <div className="relative mt-2">
              <pre className="overflow-x-auto rounded bg-bg/80 p-2 pr-9 font-mono text-xs">
                {justCreated.plaintext}
              </pre>
              <button
                onClick={onCopyKey}
                className="absolute right-1.5 top-1.5 rounded p-1 text-slate-400 transition hover:bg-bg-elevated hover:text-white"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
              </button>
            </div>
            <button
              className="mt-2 text-xs text-slate-400 hover:text-white"
              onClick={() => setJustCreated(null)}
            >
              Dismiss
            </button>
          </div>
        )}

        <div className="mt-4 overflow-hidden rounded-md">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Created</th>
                <th>Last used</th>
                <th>Expires</th>
                <th className="text-right"></th>
              </tr>
            </thead>
            <tbody>
              {tokens.isLoading &&
                Array.from({ length: 2 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={5} className="py-2">
                      <Skeleton className="h-5" />
                    </td>
                  </tr>
                ))}
              {!tokens.isLoading &&
                tokens.data?.map((t) => (
                  <tr key={t.id}>
                    <td className="font-medium text-slate-100">{t.name}</td>
                    <td className="text-xs text-slate-400">
                      {new Date(t.created_at).toLocaleString()}
                    </td>
                    <td className="text-xs text-slate-400">
                      {t.last_used_at
                        ? new Date(t.last_used_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="text-xs text-slate-400">
                      {t.expires_at
                        ? new Date(t.expires_at).toLocaleString()
                        : "never"}
                    </td>
                    <td className="text-right">
                      <button
                        className="text-xs text-severity-critical hover:underline"
                        onClick={() => setPendingRevoke(t)}
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              {!tokens.isLoading && tokens.data?.length === 0 && (
                <tr>
                  <td colSpan={5}>
                    <EmptyState
                      icon={Key}
                      title="No tokens yet"
                      description="Create one to enable CI/CD integration."
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="card">
          <div className="mb-2 flex items-center gap-2">
            <Bell className="h-4 w-4 text-amber-400" />
            <h2 className="text-sm font-semibold">Notifications</h2>
          </div>
          <p className="text-xs text-slate-400">
            Slack / Microsoft Teams / Email / Webhook delivery — configurable
            per project with severity threshold.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="chip">Slack</span>
            <span className="chip">Teams</span>
            <span className="chip">Email</span>
            <span className="chip">Webhook</span>
          </div>
        </section>

        <section className="card">
          <div className="mb-2 flex items-center gap-2">
            <BugIcon className="h-4 w-4 text-severity-high" />
            <h2 className="text-sm font-semibold">Issue trackers</h2>
          </div>
          <p className="text-xs text-slate-400">
            Bidirectional sync with bug-tracking tools — open issues for
            findings and reflect ticket status back into Cobweb.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className="chip">Jira</span>
            <span className="chip">GitHub</span>
            <span className="chip">GitLab</span>
          </div>
        </section>
      </div>

      <ConfirmDialog
        open={!!pendingRevoke}
        title={
          pendingRevoke ? `Revoke token "${pendingRevoke.name}"?` : "Revoke token?"
        }
        description={
          <>
            Any CI job, script, or 3rd-party integration using this key will start
            failing immediately. You cannot undo this — issue a new token if you
            need to restore access.
          </>
        }
        confirmLabel="Revoke token"
        tone="danger"
        loading={revoke.isPending}
        onConfirm={() => {
          if (pendingRevoke) {
            revoke.mutate(pendingRevoke.id, {
              onSuccess: () => setPendingRevoke(null),
            });
          }
        }}
        onClose={() => !revoke.isPending && setPendingRevoke(null)}
      />
    </div>
  );
}
