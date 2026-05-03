"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Plus, ScanLine, Search, Square, Trash2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import {
  EngineBadge,
  StatusPill,
} from "@/components/ui/Badges";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

interface Scan {
  id: string;
  target_id: string;
  project_id: string;
  profile: string;
  engine: string;
  status: string;
  progress: number;
  summary: Record<string, number>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

interface Target {
  id: string;
  project_id: string;
  name: string;
  base_url: string;
  status: string;
}

interface Project {
  id: string;
  name: string;
}

const STATUSES = ["queued", "running", "completed", "failed", "cancelled"];

export default function ScansPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [targetId, setTargetId] = useState("");
  const [profile, setProfile] = useState("quick");
  const [engine, setEngine] = useState<"nuclei" | "zap">("nuclei");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const scans = useQuery({
    queryKey: ["scans"],
    queryFn: () => api<Scan[]>("/api/v1/scans"),
    refetchInterval: 5_000,
  });

  // Always fetch all targets for name resolution in the table
  const allTargets = useQuery({
    queryKey: ["targets-all"],
    queryFn: () => api<Target[]>("/api/v1/targets"),
  });
  const targetMap = useMemo(() => {
    const m = new Map<string, Target>();
    allTargets.data?.forEach((t) => m.set(t.id, t));
    return m;
  }, [allTargets.data]);

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/api/v1/projects"),
    enabled: open,
  });

  const create = useMutation({
    mutationFn: (body: { target_id: string; profile: string; engine: string }) =>
      api<Scan>("/api/v1/scans", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (newScan) => {
      qc.invalidateQueries({ queryKey: ["scans"] });
      setOpen(false);
      setTargetId("");
      toast.push({
        kind: "success",
        title: "Scan queued",
        description: "Opening live view…",
      });
      // Jump straight to detail so the user sees the scan they just triggered,
      // bypassing any active filter on the list page.
      router.push(`/scans/${newScan.id}`);
    },
    onError: (err) => {
      toast.push({
        kind: "error",
        title: "Failed to start scan",
        description: err instanceof ApiError ? err.message : undefined,
      });
    },
  });

  const [confirm, setConfirm] = useState<
    | { kind: "cancel"; scan: Scan }
    | { kind: "delete"; scan: Scan }
    | null
  >(null);

  const cancelMut = useMutation({
    mutationFn: (id: string) =>
      api<Scan>(`/api/v1/scans/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scans"] });
      setConfirm(null);
      toast.push({ kind: "success", title: "Scan cancelled" });
    },
    onError: (err) => {
      toast.push({
        kind: "error",
        title: "Failed to cancel scan",
        description: err instanceof ApiError ? err.message : undefined,
      });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) =>
      api(`/api/v1/scans/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scans"] });
      qc.invalidateQueries({ queryKey: ["vulnerabilities"] });
      setConfirm(null);
      toast.push({ kind: "success", title: "Scan deleted" });
    },
    onError: (err) => {
      toast.push({
        kind: "error",
        title: "Failed to delete scan",
        description: err instanceof ApiError ? err.message : undefined,
      });
    },
  });

  const filteredScans = (scans.data ?? []).filter((s) => {
    if (statusFilter && s.status !== statusFilter) return false;
    if (search) {
      const t = targetMap.get(s.target_id);
      const haystack = [
        s.id,
        s.target_id,
        s.profile,
        s.engine,
        t?.name ?? "",
        t?.base_url ?? "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(search.toLowerCase())) return false;
    }
    return true;
  });

  const verifiedTargets = (allTargets.data ?? []).filter(
    (t) => t.status === "verified",
  );

  return (
    <div>
      <PageHeader
        title="Scans"
        description="Active and historical scans across your projects."
        action={
          <button
            className="btn-primary"
            onClick={() => setOpen(true)}
          >
            <Plus className="h-4 w-4" />
            New scan
          </button>
        }
      />

      {open && (
        <div className="card mb-4 animate-fade-in">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Configure scan</h3>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-slate-400 hover:text-white"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <form
            className="grid gap-3 md:grid-cols-2 lg:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (targetId)
                create.mutate({ target_id: targetId, profile, engine });
            }}
          >
            <label className="md:col-span-2">
              <span className="label">Target</span>
              <select
                className="input"
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                required
              >
                <option value="">— pick a verified target —</option>
                {verifiedTargets.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} · {t.base_url}
                  </option>
                ))}
                {allTargets.data && allTargets.data.length > 0 && verifiedTargets.length === 0 && (
                  <option disabled>No verified targets · verify one first</option>
                )}
              </select>
            </label>
            <label>
              <span className="label">Engine</span>
              <select
                className="input"
                value={engine}
                onChange={(e) => setEngine(e.target.value as "nuclei" | "zap")}
              >
                <option value="nuclei">Nuclei · template-based, fast</option>
                <option value="zap">OWASP ZAP · spider + active scan</option>
              </select>
            </label>
            <label>
              <span className="label">Profile</span>
              <select
                className="input"
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
              >
                <option value="quick">
                  Quick · tech + misconfig + exposure (1–3 min)
                </option>
                <option value="high">
                  High · CVE templates, medium+ severity (5–15 min)
                </option>
                <option value="full">
                  Full · every template, no filter (30+ min)
                </option>
                <option value="custom">Custom (advanced)</option>
              </select>
            </label>
            <div className="md:col-span-2 lg:col-span-4 flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setOpen(false)}
              >
                Cancel
              </button>
              <button
                className="btn-primary"
                disabled={create.isPending || !targetId}
              >
                {create.isPending ? "Queuing…" : "Start scan"}
              </button>
            </div>
          </form>
          {projects.error && (
            <p className="mt-2 text-xs text-severity-critical">
              Failed to load projects
            </p>
          )}
        </div>
      )}

      {/* Filter bar */}
      <div className="card mb-3 flex flex-wrap items-center gap-2 p-2.5">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
          <input
            className="input !pl-8"
            placeholder="Search by target, profile, id…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="input w-auto"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {(search || statusFilter) && (
          <button
            className="btn-ghost text-xs"
            onClick={() => {
              setSearch("");
              setStatusFilter("");
            }}
          >
            Clear
          </button>
        )}
      </div>

      <div className="card overflow-hidden p-0">
        <table className="table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Target</th>
              <th>Engine</th>
              <th>Profile</th>
              <th>Progress</th>
              <th>Findings</th>
              <th>Started</th>
              <th className="w-px"></th>
            </tr>
          </thead>
          <tbody>
            {scans.isLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i}>
                  <td colSpan={8} className="py-2">
                    <Skeleton className="h-5 w-full" />
                  </td>
                </tr>
              ))}
            {!scans.isLoading &&
              filteredScans.map((s) => {
                const target = targetMap.get(s.target_id);
                return (
                  <tr key={s.id}>
                    <td>
                      <Link
                        href={`/scans/${s.id}`}
                        className="inline-flex items-center"
                      >
                        <StatusPill status={s.status} />
                      </Link>
                    </td>
                    <td>
                      {target ? (
                        <div className="min-w-0">
                          <Link
                            href={`/scans/${s.id}`}
                            className="block truncate font-medium text-slate-100 hover:text-accent"
                          >
                            {target.name}
                          </Link>
                          <span className="block truncate font-mono text-[11px] text-slate-500">
                            {target.base_url}
                          </span>
                        </div>
                      ) : (
                        <span className="font-mono text-xs text-slate-400">
                          {s.target_id.slice(0, 8)}…
                        </span>
                      )}
                    </td>
                    <td>
                      <EngineBadge engine={s.engine} />
                    </td>
                    <td className="text-slate-300">{s.profile}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        <ProgressBar
                          progress={s.progress}
                          status={s.status}
                          size="sm"
                          className="w-24"
                        />
                        <span className="font-mono text-[11px] text-slate-500">
                          {s.progress}%
                        </span>
                      </div>
                    </td>
                    <td>
                      <SeverityCounts summary={s.summary} />
                    </td>
                    <td className="text-xs text-slate-400">
                      {s.started_at
                        ? new Date(s.started_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="text-right">
                      {(s.status === "queued" || s.status === "running") ? (
                        <button
                          type="button"
                          onClick={() => setConfirm({ kind: "cancel", scan: s })}
                          className="rounded-md p-1.5 text-slate-500 transition hover:bg-severity-medium/15 hover:text-severity-medium"
                          aria-label="Stop scan"
                          title="Stop scan"
                        >
                          <Square className="h-4 w-4" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setConfirm({ kind: "delete", scan: s })}
                          className="rounded-md p-1.5 text-slate-500 transition hover:bg-severity-critical/15 hover:text-severity-critical"
                          aria-label="Delete scan"
                          title="Delete scan"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            {!scans.isLoading && filteredScans.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <EmptyState
                    icon={ScanLine}
                    title={
                      search || statusFilter
                        ? "No scans match your filter"
                        : "No scans yet"
                    }
                    description={
                      search || statusFilter
                        ? "Adjust filters to see more."
                        : "Pick a verified target and run your first scan."
                    }
                    action={
                      !search && !statusFilter ? (
                        <button
                          className="btn-primary text-sm"
                          onClick={() => setOpen(true)}
                        >
                          <Plus className="h-3.5 w-3.5" />
                          New scan
                        </button>
                      ) : null
                    }
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={confirm?.kind === "cancel"}
        title="Stop this scan?"
        description={
          confirm?.kind === "cancel" ? (
            <>
              The worker will terminate within a few seconds. Findings collected so
              far are kept; the scan is marked as <em>cancelled</em>.
            </>
          ) : null
        }
        confirmLabel="Stop scan"
        cancelLabel="Keep running"
        tone="warning"
        loading={cancelMut.isPending}
        onConfirm={() => {
          if (confirm?.kind === "cancel") cancelMut.mutate(confirm.scan.id);
        }}
        onClose={() => !cancelMut.isPending && setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm?.kind === "delete"}
        title="Delete this scan?"
        description={
          confirm?.kind === "delete" ? (
            <>
              All findings from this run will be removed. Vulnerabilities aggregated
              across other scans are not affected. This cannot be undone.
            </>
          ) : null
        }
        confirmLabel="Delete scan"
        tone="danger"
        loading={deleteMut.isPending}
        onConfirm={() => {
          if (confirm?.kind === "delete") deleteMut.mutate(confirm.scan.id);
        }}
        onClose={() => !deleteMut.isPending && setConfirm(null)}
      />
    </div>
  );
}

function SeverityCounts({ summary }: { summary: Record<string, number> }) {
  const keys = ["critical", "high", "medium", "low", "info"] as const;
  const total = keys.reduce((acc, k) => acc + (summary?.[k] ?? 0), 0);
  if (total === 0) return <span className="text-xs text-slate-500">—</span>;
  return (
    <div className="flex items-center gap-1">
      {keys.map((k) => {
        const n = summary?.[k] ?? 0;
        if (!n) return null;
        return (
          <span
            key={k}
            title={`${k}: ${n}`}
            className={`inline-flex h-5 min-w-[1.4rem] items-center justify-center rounded px-1 text-[10px] font-mono font-semibold text-severity-${k} bg-severity-${k}/15`}
          >
            {n}
          </span>
        );
      })}
    </div>
  );
}
