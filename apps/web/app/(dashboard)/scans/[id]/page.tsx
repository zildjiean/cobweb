"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  Clock,
  ExternalLink,
  Radio,
  Activity,
  Square,
  Trash2,
  X as XIcon,
} from "lucide-react";
import { api, ApiError, tokenStore, wsUrl } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import FindingDetailModal from "@/components/FindingDetailModal";
import {
  EngineBadge,
  SeverityPill,
  StatusPill,
} from "@/components/ui/Badges";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";
import { ProgressBar, formatEta } from "@/components/ui/ProgressBar";
import ConfirmDialog from "@/components/ui/ConfirmDialog";

interface Scan {
  id: string;
  target_id: string;
  profile: string;
  engine: string;
  status: string;
  progress: number;
  template_version: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  summary: Record<string, number>;
  created_at: string;
}

interface Finding {
  id: string;
  scan_id: string;
  template_id: string;
  name: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  matched_at: string;
  description: string | null;
  remediation: string | null;
  cve: string | null;
  created_at: string;
}

interface Target {
  id: string;
  name: string;
  base_url: string;
  status: string;
}

const SEV_ORDER: Finding["severity"][] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
];

interface LiveEvent {
  type: string;
  payload?: Record<string, unknown>;
  ts: string;
}

export default function ScanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: scanId } = use(params);
  const qc = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [openFindingId, setOpenFindingId] = useState<string | null>(null);
  const [filterSev, setFilterSev] = useState<string>("");
  const [confirm, setConfirm] = useState<"cancel" | "delete" | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pendingFindingDelete, setPendingFindingDelete] = useState<
    Finding[] | null
  >(null);
  const wsRef = useRef<WebSocket | null>(null);

  const scan = useQuery({
    queryKey: ["scan", scanId],
    queryFn: () => api<Scan>(`/api/v1/scans/${scanId}`),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "running" ? 3_000 : false;
    },
  });

  const findings = useQuery({
    queryKey: ["findings", scanId],
    queryFn: () => api<Finding[]>(`/api/v1/scans/${scanId}/findings`),
    refetchInterval: (q) => (scan.data?.status === "running" ? 5_000 : false),
  });

  const targets = useQuery({
    queryKey: ["targets-all"],
    queryFn: () => api<Target[]>("/api/v1/targets"),
  });
  const target = useMemo(
    () => targets.data?.find((t) => t.id === scan.data?.target_id) ?? null,
    [targets.data, scan.data?.target_id],
  );

  const cancelMut = useMutation({
    mutationFn: () =>
      api<Scan>(`/api/v1/scans/${scanId}/cancel`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scan", scanId] });
      qc.invalidateQueries({ queryKey: ["scans"] });
      setConfirm(null);
      toast.push({ kind: "success", title: "Scan cancelled" });
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Failed to cancel scan",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  const deleteMut = useMutation({
    mutationFn: () => api(`/api/v1/scans/${scanId}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scans"] });
      qc.invalidateQueries({ queryKey: ["vulnerabilities"] });
      toast.push({ kind: "success", title: "Scan deleted" });
      router.replace("/scans");
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Failed to delete scan",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  const bulkDeleteFindingsMut = useMutation({
    mutationFn: (ids: string[]) =>
      api<{ deleted: number; summary: Record<string, number> }>(
        `/api/v1/scans/${scanId}/findings/_delete`,
        { method: "POST", body: JSON.stringify({ ids }) },
      ),
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ["findings", scanId] });
      qc.invalidateQueries({ queryKey: ["scan", scanId] });
      qc.invalidateQueries({ queryKey: ["scans"] });
      qc.invalidateQueries({ queryKey: ["vulnerabilities"] });
      setSelected(new Set());
      setPendingFindingDelete(null);
      toast.push({
        kind: "success",
        title:
          resp.deleted === 1
            ? "Finding deleted"
            : `${resp.deleted} findings deleted`,
      });
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Failed to delete findings",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  useEffect(() => {
    const token = tokenStore.get();
    if (!token) return;
    const url =
      wsUrl(`/api/v1/ws/scans/${scanId}`) +
      `?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data);
        setEvents((prev) =>
          [{ ...ev, ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 80),
        );
        if (ev.type === "status" || ev.type === "progress") {
          qc.invalidateQueries({ queryKey: ["scan", scanId] });
        }
        if (ev.type === "finding") {
          qc.invalidateQueries({ queryKey: ["findings", scanId] });
        }
      } catch {
        /* ignore non-JSON */
      }
    };

    return () => ws.close();
  }, [scanId, qc]);

  if (scan.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }
  if (scan.error) {
    return (
      <p className="text-severity-critical">
        {scan.error instanceof ApiError ? scan.error.message : "Error"}
      </p>
    );
  }
  if (!scan.data) return null;
  const s = scan.data;

  const duration =
    s.started_at && s.finished_at
      ? Math.max(
          0,
          Math.round(
            (new Date(s.finished_at).getTime() -
              new Date(s.started_at).getTime()) /
              1000,
          ),
        )
      : null;

  const filteredFindings = (findings.data ?? [])
    .filter((f) => !filterSev || f.severity === filterSev)
    .slice()
    .sort(
      (a, b) =>
        SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity),
    );

  return (
    <div className="space-y-5">
      <PageHeader
        title={`Scan ${s.id.slice(0, 8)}`}
        description={
          target ? `${target.name} · ${target.base_url}` : "Scan detail"
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/scans" className="btn-ghost text-sm">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to scans
            </Link>
            {(s.status === "queued" || s.status === "running") ? (
              <button
                type="button"
                onClick={() => setConfirm("cancel")}
                className="btn text-sm bg-severity-medium/15 text-severity-medium hover:bg-severity-medium/25"
              >
                <Square className="h-3.5 w-3.5" />
                Stop scan
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setConfirm("delete")}
                className="btn-danger text-sm"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete scan
              </button>
            )}
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        {/* Overview */}
        <div className="card md:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="section-title">Overview</h2>
            <div className="flex items-center gap-2">
              <EngineBadge engine={s.engine} />
              <StatusPill status={s.status} />
            </div>
          </div>
          <dl className="grid grid-cols-1 gap-y-2 text-sm md:grid-cols-2">
            <Row label="Profile" value={s.profile} />
            <Row label="Target" value={target?.base_url ?? s.target_id} mono />
            <Row label="Template version" value={s.template_version ?? "—"} mono />
            <Row
              label="Started"
              value={s.started_at ? new Date(s.started_at).toLocaleString() : "—"}
            />
            <Row
              label="Finished"
              value={s.finished_at ? new Date(s.finished_at).toLocaleString() : "—"}
            />
            <Row
              label="Duration"
              value={duration !== null ? formatDuration(duration) : "—"}
            />
          </dl>
          <div className="mt-4">
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-slate-400">
                Progress
                {(s.status === "running" || s.status === "queued") && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                    ·
                    <span className="text-emerald-300">
                      {formatEta(s.started_at, s.progress, s.profile, s.status) ??
                        "warming up…"}
                    </span>
                  </span>
                )}
              </span>
              <span className="font-mono text-slate-200">{s.progress}%</span>
            </div>
            <ProgressBar progress={s.progress} status={s.status} />
          </div>
          {s.error_message && (
            <p className="mt-3 rounded-md border border-severity-critical/40 bg-severity-critical/10 p-2.5 text-xs text-severity-critical">
              {s.error_message}
            </p>
          )}
        </div>

        {/* Severity counts */}
        <div className="card">
          <h2 className="section-title mb-3">Findings by severity</h2>
          <div className="grid grid-cols-5 gap-2">
            {SEV_ORDER.map((sev) => (
              <button
                key={sev}
                onClick={() => setFilterSev(filterSev === sev ? "" : sev)}
                className={`rounded-md border bg-bg/40 p-2 text-center transition ${
                  filterSev === sev
                    ? `border-severity-${sev}/40 ring-2 ring-severity-${sev}/40`
                    : "border-border-subtle hover:border-border"
                }`}
              >
                <div className={`text-xl font-bold text-severity-${sev}`}>
                  {s.summary?.[sev] ?? 0}
                </div>
                <div className="text-[10px] uppercase tracking-wide text-slate-400">
                  {sev}
                </div>
              </button>
            ))}
          </div>
          {filterSev && (
            <p className="mt-2 text-[11px] text-slate-500">
              Filtering findings by{" "}
              <span className={`text-severity-${filterSev}`}>{filterSev}</span> ·{" "}
              <button
                className="underline"
                onClick={() => setFilterSev("")}
              >
                clear
              </button>
            </p>
          )}
        </div>
      </div>

      {/* Findings */}
      <div className="card">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="section-title">
            Findings ({filteredFindings.length}
            {filterSev ? ` of ${findings.data?.length ?? 0}` : ""})
          </h2>
          <span className="text-[11px] text-slate-500">
            Click a row for full request / response / payload
          </span>
        </div>

        {selected.size > 0 && (
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-accent/30 bg-accent/10 px-3 py-2 animate-fade-in">
            <span className="text-sm text-slate-200">
              <span className="font-mono font-semibold text-accent">
                {selected.size}
              </span>{" "}
              {selected.size === 1 ? "finding" : "findings"} selected
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn-ghost text-xs"
                onClick={() => setSelected(new Set())}
              >
                <XIcon className="h-3.5 w-3.5" />
                Clear
              </button>
              <button
                type="button"
                className="btn text-xs bg-severity-critical/15 text-severity-critical hover:bg-severity-critical/25"
                onClick={() =>
                  setPendingFindingDelete(
                    filteredFindings.filter((f) => selected.has(f.id)),
                  )
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete {selected.size}
              </button>
            </div>
          </div>
        )}

        <div className="overflow-hidden rounded-md">
          <table className="table">
            <thead>
              <tr>
                <th className="w-px pr-0">
                  <input
                    type="checkbox"
                    aria-label="Select all visible findings"
                    className="h-3.5 w-3.5 cursor-pointer accent-accent"
                    ref={(el) => {
                      if (!el) return;
                      const visible = filteredFindings.length;
                      const picked = filteredFindings.filter((f) =>
                        selected.has(f.id),
                      ).length;
                      el.checked = visible > 0 && picked === visible;
                      el.indeterminate = picked > 0 && picked < visible;
                    }}
                    onChange={(e) => {
                      const next = new Set(selected);
                      if (e.target.checked) {
                        filteredFindings.forEach((f) => next.add(f.id));
                      } else {
                        filteredFindings.forEach((f) => next.delete(f.id));
                      }
                      setSelected(next);
                    }}
                  />
                </th>
                <th>Severity</th>
                <th>Name</th>
                <th>Template</th>
                <th>Matched at</th>
                <th>CVE</th>
                <th className="w-px"></th>
              </tr>
            </thead>
            <tbody>
              {findings.isLoading &&
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i}>
                    <td colSpan={7} className="py-2">
                      <Skeleton className="h-5 w-full" />
                    </td>
                  </tr>
                ))}
              {!findings.isLoading &&
                filteredFindings.map((f) => {
                  const isSelected = selected.has(f.id);
                  return (
                    <tr
                      key={f.id}
                      className={`cursor-pointer ${isSelected ? "bg-accent/5" : ""}`}
                      onClick={() => setOpenFindingId(f.id)}
                      title="View full payload"
                    >
                      <td
                        className="pr-0"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${f.name}`}
                          className="h-3.5 w-3.5 cursor-pointer accent-accent"
                          checked={isSelected}
                          onChange={(e) => {
                            const next = new Set(selected);
                            if (e.target.checked) next.add(f.id);
                            else next.delete(f.id);
                            setSelected(next);
                          }}
                        />
                      </td>
                      <td>
                        <SeverityPill severity={f.severity} />
                      </td>
                      <td className="font-medium text-slate-100">{f.name}</td>
                      <td className="font-mono text-xs text-slate-400">
                        {f.template_id}
                      </td>
                      <td className="font-mono text-xs text-slate-400">
                        <span className="inline-flex items-center gap-1">
                          {f.matched_at}
                          <ExternalLink className="h-3 w-3 opacity-50" />
                        </span>
                      </td>
                      <td className="font-mono text-xs text-slate-400">
                        {f.cve ?? "—"}
                      </td>
                      <td
                        className="text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          type="button"
                          onClick={() => setPendingFindingDelete([f])}
                          className="rounded-md p-1.5 text-slate-500 transition hover:bg-severity-critical/15 hover:text-severity-critical"
                          aria-label={`Delete ${f.name}`}
                          title="Delete this finding"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              {!findings.isLoading && filteredFindings.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      icon={Activity}
                      title={
                        filterSev
                          ? `No ${filterSev} findings`
                          : s.status === "running" || s.status === "queued"
                          ? "Scanning…"
                          : "No findings"
                      }
                      description={
                        filterSev
                          ? "Try clearing the severity filter."
                          : "Findings will stream in as they are detected."
                      }
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <DiffPanel scanId={scanId} status={s.status} />

      {/* Live event stream */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="section-title flex items-center gap-2">
            <Radio
              className={`h-3.5 w-3.5 ${
                s.status === "running" || s.status === "queued"
                  ? "text-emerald-400"
                  : "text-slate-500"
              }`}
            />
            Live event stream
          </h2>
          <span className="text-[11px] text-slate-500">
            {events.length} events
          </span>
        </div>
        <div className="max-h-64 overflow-auto rounded-md bg-bg/60 p-2 font-mono text-[11px] leading-relaxed">
          {events.length === 0 && (
            <span className="text-slate-500">
              Waiting for events… (WebSocket connected)
            </span>
          )}
          {events.map((e, i) => (
            <div
              key={i}
              className="border-b border-border-subtle/30 py-0.5 last:border-0"
            >
              <span className="text-slate-500">[{e.ts}]</span>{" "}
              <span
                className={
                  e.type === "finding"
                    ? "text-severity-medium"
                    : e.type === "status"
                    ? "text-accent"
                    : e.type === "progress"
                    ? "text-emerald-300"
                    : "text-slate-300"
                }
              >
                {e.type}
              </span>{" "}
              <span className="text-slate-400">{JSON.stringify(e.payload ?? {})}</span>
            </div>
          ))}
        </div>
      </div>

      <FindingDetailModal
        scanId={scanId}
        findingId={openFindingId}
        onClose={() => setOpenFindingId(null)}
      />

      <ConfirmDialog
        open={confirm === "cancel"}
        title="Stop this scan?"
        description={
          <>
            The worker terminates within a few seconds. Findings already collected
            stay; the scan is marked as <em>cancelled</em>.
          </>
        }
        confirmLabel="Stop scan"
        cancelLabel="Keep running"
        tone="warning"
        loading={cancelMut.isPending}
        onConfirm={() => cancelMut.mutate()}
        onClose={() => !cancelMut.isPending && setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "delete"}
        title="Delete this scan?"
        description={
          <>
            All {findings.data?.length ?? 0} findings from this run will be removed.
            Vulnerabilities aggregated across other scans are not affected. This
            cannot be undone.
          </>
        }
        confirmLabel="Delete scan"
        tone="danger"
        loading={deleteMut.isPending}
        onConfirm={() => deleteMut.mutate()}
        onClose={() => !deleteMut.isPending && setConfirm(null)}
      />

      <ConfirmDialog
        open={!!pendingFindingDelete && pendingFindingDelete.length > 0}
        title={
          pendingFindingDelete?.length === 1
            ? "Delete this finding?"
            : `Delete ${pendingFindingDelete?.length ?? 0} findings?`
        }
        description={
          pendingFindingDelete && pendingFindingDelete.length > 0 ? (
            <div className="space-y-2">
              <p>
                Removed from this scan and the severity counts adjust. Vulnerabilities
                aggregated from other scans are unaffected. This cannot be undone.
              </p>
              <ul className="rounded-md border border-border-subtle bg-bg/40 p-2 text-xs">
                {pendingFindingDelete.slice(0, 3).map((f) => (
                  <li key={f.id} className="flex items-center gap-2 truncate">
                    <SeverityPill severity={f.severity} />
                    <span className="truncate text-slate-200">{f.name}</span>
                  </li>
                ))}
                {pendingFindingDelete.length > 3 && (
                  <li className="mt-1 text-slate-500">
                    … and {pendingFindingDelete.length - 3} more
                  </li>
                )}
              </ul>
            </div>
          ) : null
        }
        confirmLabel={
          pendingFindingDelete && pendingFindingDelete.length > 1
            ? `Delete ${pendingFindingDelete.length}`
            : "Delete finding"
        }
        tone="danger"
        loading={bulkDeleteFindingsMut.isPending}
        onConfirm={() => {
          if (pendingFindingDelete && pendingFindingDelete.length > 0) {
            bulkDeleteFindingsMut.mutate(pendingFindingDelete.map((f) => f.id));
          }
        }}
        onClose={() =>
          !bulkDeleteFindingsMut.isPending && setPendingFindingDelete(null)
        }
      />
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
}) {
  return (
    <>
      <dt className="text-xs text-slate-400">{label}</dt>
      <dd
        className={`break-all text-slate-200 ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value || "—"}
      </dd>
    </>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

interface DiffEntry {
  dedupe_hash: string;
  template_id: string;
  name: string;
  severity: Finding["severity"];
  matched_at: string;
  category: string;
}

interface DiffResponse {
  base_scan_id: string | null;
  head_scan_id: string;
  new: DiffEntry[];
  fixed: DiffEntry[];
  recurring: DiffEntry[];
  regression: DiffEntry[];
}

function DiffPanel({ scanId, status }: { scanId: string; status: string }) {
  const diff = useQuery({
    queryKey: ["diff", scanId],
    queryFn: () => api<DiffResponse>(`/api/v1/scans/${scanId}/diff`),
    enabled: status === "completed" || status === "failed",
  });

  if (!diff.data) return null;
  if (!diff.data.base_scan_id) {
    return (
      <div className="card">
        <h2 className="section-title mb-2">Diff vs previous</h2>
        <p className="flex items-center gap-2 text-xs text-slate-500">
          <Clock className="h-3.5 w-3.5" />
          No previous scan for this target — this is the baseline.
        </p>
      </div>
    );
  }
  const cats = [
    { k: "new" as const, label: "New", tone: "text-severity-critical", border: "border-severity-critical/30 bg-severity-critical/5" },
    { k: "regression" as const, label: "Regression", tone: "text-severity-high", border: "border-severity-high/30 bg-severity-high/5" },
    { k: "fixed" as const, label: "Fixed", tone: "text-severity-low", border: "border-severity-low/30 bg-severity-low/5" },
    { k: "recurring" as const, label: "Recurring", tone: "text-slate-300", border: "border-border" },
  ];
  return (
    <div className="card">
      <h2 className="section-title mb-3">
        Diff vs previous scan ·{" "}
        <Link
          href={`/scans/${diff.data.base_scan_id}`}
          className="font-mono text-accent hover:underline"
        >
          {diff.data.base_scan_id?.slice(0, 8)}
        </Link>
      </h2>
      <div className="grid gap-3 md:grid-cols-4">
        {cats.map((c) => (
          <div
            key={c.k}
            className={`rounded-lg border p-3 ${c.border}`}
          >
            <div className={`text-2xl font-bold ${c.tone}`}>
              {diff.data![c.k].length}
            </div>
            <div className="text-[10px] uppercase tracking-wide text-slate-400">
              {c.label}
            </div>
            <ul className="mt-2 space-y-1 text-xs text-slate-300">
              {diff.data![c.k].slice(0, 5).map((e) => (
                <li
                  key={`${c.k}-${e.dedupe_hash}`}
                  className="truncate"
                  title={e.name}
                >
                  • {e.name}
                </li>
              ))}
              {diff.data![c.k].length > 5 && (
                <li className="text-slate-500">
                  … +{diff.data![c.k].length - 5} more
                </li>
              )}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
