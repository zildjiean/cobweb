"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, Copy, Plus, Target as TargetIcon, Trash2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { StatusPill } from "@/components/ui/Badges";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

interface Project {
  id: string;
  name: string;
  slug: string;
}

interface Target {
  id: string;
  project_id: string;
  name: string;
  base_url: string;
  status: string;
  verification_token: string | null;
}

export default function TargetsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [activeProject, setActiveProject] = useState<string>("");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<Target | null>(null);

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/api/v1/projects"),
  });

  const targets = useQuery({
    queryKey: ["targets", activeProject],
    queryFn: () => api<Target[]>(`/api/v1/projects/${activeProject}/targets`),
    enabled: !!activeProject,
  });

  const create = useMutation({
    mutationFn: (body: { name: string; base_url: string }) =>
      api<Target>(`/api/v1/projects/${activeProject}/targets`, {
        method: "POST",
        body: JSON.stringify({
          ...body,
          scope_includes: [],
          scope_excludes: [],
        }),
      }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["targets", activeProject] });
      qc.invalidateQueries({ queryKey: ["targets-all"] });
      toast.push({
        kind: "success",
        title:
          created.status === "verified"
            ? "Target added & auto-verified (dev mode)"
            : "Target added — verify ownership next",
      });
      setName("");
      setBaseUrl("");
      setShowAddForm(false);
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Failed to add target",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  const verify = useMutation({
    mutationFn: (id: string) =>
      api<Target>(`/api/v1/targets/${id}/verify`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["targets", activeProject] });
      qc.invalidateQueries({ queryKey: ["targets-all"] });
      toast.push({ kind: "success", title: "Target verified" });
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Verification failed",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/api/v1/targets/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["targets", activeProject] });
      qc.invalidateQueries({ queryKey: ["targets-all"] });
      qc.invalidateQueries({ queryKey: ["scans"] });
      qc.invalidateQueries({ queryKey: ["vulnerabilities"] });
      toast.push({ kind: "success", title: "Target deleted" });
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Failed to delete target",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  return (
    <div>
      <PageHeader
        title="Targets"
        description="Web applications under scope. Verify ownership before scanning."
      />

      <div className="card mb-4 flex flex-wrap items-end gap-3">
        <label className="flex-1 min-w-[220px]">
          <span className="label">Project</span>
          <select
            className="input"
            value={activeProject}
            onChange={(e) => setActiveProject(e.target.value)}
          >
            <option value="">— select a project —</option>
            {projects.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {activeProject && (
          <button
            className="btn-primary"
            onClick={() => setShowAddForm(!showAddForm)}
          >
            <Plus className="h-4 w-4" />
            Add target
          </button>
        )}
      </div>

      {!activeProject && (
        <div className="card">
          <EmptyState
            icon={TargetIcon}
            title="Pick a project"
            description="Targets are scoped to a project. Select one to view or add."
          />
        </div>
      )}

      {activeProject && showAddForm && (
        <div className="card mb-4 animate-fade-in">
          <h3 className="mb-3 text-sm font-semibold">New target</h3>
          <form
            className="grid gap-3 md:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate({ name, base_url: baseUrl });
            }}
          >
            <label>
              <span className="label">Name</span>
              <input
                className="input"
                placeholder="Production website"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label className="md:col-span-2">
              <span className="label">Base URL</span>
              <input
                className="input"
                placeholder="https://example.com"
                value={baseUrl}
                type="url"
                onChange={(e) => setBaseUrl(e.target.value)}
                required
              />
            </label>
            <div className="md:col-span-3 flex justify-end gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setShowAddForm(false)}
              >
                Cancel
              </button>
              <button className="btn-primary" disabled={create.isPending}>
                {create.isPending ? "Adding…" : "Add target"}
              </button>
            </div>
          </form>
        </div>
      )}

      {activeProject && targets.isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {activeProject && targets.data && targets.data.length === 0 && (
        <div className="card">
          <EmptyState
            icon={TargetIcon}
            title="No targets in this project"
            description="Add a target to begin running scans."
            action={
              <button
                className="btn-primary text-sm"
                onClick={() => setShowAddForm(true)}
              >
                <Plus className="h-3.5 w-3.5" />
                Add target
              </button>
            }
          />
        </div>
      )}

      <div className="space-y-3">
        {targets.data?.map((t) => (
          <TargetCard
            key={t.id}
            target={t}
            onVerify={() => verify.mutate(t.id)}
            verifying={verify.isPending && verify.variables === t.id}
            onDelete={() => setPendingDelete(t)}
            deleting={remove.isPending && remove.variables === t.id}
          />
        ))}
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        title={
          pendingDelete ? `Delete target "${pendingDelete.name}"?` : "Delete target?"
        }
        description={
          <>
            This cascades — every scan, finding, and vulnerability for{" "}
            <span className="font-mono text-slate-200">
              {pendingDelete?.base_url}
            </span>{" "}
            is removed. This cannot be undone.
          </>
        }
        confirmLabel="Delete target"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => {
          if (pendingDelete) {
            remove.mutate(pendingDelete.id, {
              onSuccess: () => setPendingDelete(null),
            });
          }
        }}
        onClose={() => !remove.isPending && setPendingDelete(null)}
      />
    </div>
  );
}

function TargetCard({
  target,
  onVerify,
  verifying,
  onDelete,
  deleting,
}: {
  target: Target;
  onVerify: () => void;
  verifying: boolean;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <div className="card">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-base font-semibold">{target.name}</h3>
            <StatusPill status={target.status} />
          </div>
          <a
            href={target.base_url}
            target="_blank"
            rel="noopener"
            className="mt-1 block truncate font-mono text-xs text-slate-400 hover:text-accent"
          >
            {target.base_url}
          </a>
        </div>
        <button
          type="button"
          onClick={onDelete}
          disabled={deleting}
          className="shrink-0 rounded-md p-2 text-slate-500 transition hover:bg-severity-critical/15 hover:text-severity-critical disabled:opacity-50"
          aria-label="Delete target"
          title="Delete target (cascades to scans, findings, vulnerabilities)"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
      {target.status === "pending_verification" && target.verification_token && (
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs">
          <p className="text-slate-200">
            <strong>Prove you own this target.</strong> Do <em>one</em> of:
          </p>
          <ol className="mt-2 space-y-2 pl-4 [counter-reset:step]">
            <li className="relative pl-6 [counter-increment:step]">
              <span className="absolute left-0 top-0 flex h-4 w-4 items-center justify-center rounded-full bg-amber-500/30 text-[10px] font-bold text-amber-200">
                1
              </span>
              <p className="text-slate-300">
                Place this token at:{" "}
                <code className="text-accent">
                  {target.base_url.replace(/\/$/, "")}
                  /.well-known/cobweb-challenge
                </code>
              </p>
              <CopyableCode text={target.verification_token} />
            </li>
            <li className="relative pl-6 [counter-increment:step]">
              <span className="absolute left-0 top-0 flex h-4 w-4 items-center justify-center rounded-full bg-amber-500/30 text-[10px] font-bold text-amber-200">
                2
              </span>
              <p className="text-slate-300">
                Or paste this <code className="text-accent">&lt;meta&gt;</code> tag
                into your homepage's <code>&lt;head&gt;</code>:
              </p>
              <CopyableCode
                text={`<meta name="cobweb-site-verification" content="${target.verification_token}">`}
              />
            </li>
          </ol>
          <button
            className="btn-primary mt-3"
            onClick={onVerify}
            disabled={verifying}
          >
            {verifying ? "Checking…" : "Verify now"}
          </button>
        </div>
      )}
    </div>
  );
}

function CopyableCode({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = () => {
    navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="relative mt-1.5">
      <pre className="overflow-x-auto rounded-md bg-bg/80 p-2 pr-9 font-mono text-[11px] text-slate-200">
        {text}
      </pre>
      <button
        type="button"
        onClick={onCopy}
        className="absolute right-1.5 top-1.5 rounded p-1 text-slate-400 transition hover:bg-bg-elevated hover:text-white"
        aria-label="Copy"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}
