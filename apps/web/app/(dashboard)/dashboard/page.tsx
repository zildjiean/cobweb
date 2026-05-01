"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Bug,
  ExternalLink,
  FolderKanban,
  ScanLine,
  Target as TargetIcon,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader, Skeleton } from "@/components/ui/EmptyState";
import { HBarChart, Sparkline } from "@/components/ui/Charts";
import { EngineBadge, StatusPill } from "@/components/ui/Badges";
import { TargetFilter } from "@/components/ui/TargetFilter";

interface Scan {
  id: string;
  status: string;
  progress: number;
  engine: string;
  summary: Record<string, number>;
  created_at: string;
  finished_at: string | null;
  target_id: string;
}
interface Vuln {
  id: string;
  name: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  state: string;
  sla_due_at: string | null;
  target_id: string;
}
interface Project { id: string; name: string }
interface Target {
  id: string;
  name: string;
  base_url: string;
  project_id: string;
}

const SEV_ORDER = ["critical", "high", "medium", "low", "info"] as const;
const TERMINAL_STATES = new Set([
  "false_positive",
  "accepted_risk",
  "verified",
]);

export default function DashboardPage() {
  const [projectId, setProjectId] = useState<string>("");
  const [targetId, setTargetId] = useState<string>("");

  const scansQs = new URLSearchParams();
  if (projectId) scansQs.set("project_id", projectId);
  if (targetId) scansQs.set("target_id", targetId);

  const vulnsQs = new URLSearchParams();
  if (projectId) vulnsQs.set("project_id", projectId);
  if (targetId) vulnsQs.set("target_id", targetId);

  const scans = useQuery({
    queryKey: ["scans", projectId, targetId],
    queryFn: () =>
      api<Scan[]>(
        `/api/v1/scans${scansQs.toString() ? `?${scansQs}` : ""}`,
      ),
    refetchInterval: 10_000,
  });
  const vulns = useQuery({
    queryKey: ["vulnerabilities", projectId, targetId],
    queryFn: () =>
      api<Vuln[]>(
        `/api/v1/vulnerabilities${vulnsQs.toString() ? `?${vulnsQs}` : ""}`,
      ),
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/api/v1/projects"),
  });
  const targets = useQuery({
    queryKey: ["targets-all"],
    queryFn: () => api<Target[]>("/api/v1/targets"),
  });
  const targetMap = useMemo(() => {
    const m = new Map<string, Target>();
    targets.data?.forEach((t) => m.set(t.id, t));
    return m;
  }, [targets.data]);

  const loading = scans.isLoading || vulns.isLoading || projects.isLoading;
  const anyError = scans.error || vulns.error || projects.error;
  const isFiltered = !!targetId || !!projectId;
  const selectedTarget = targetId ? targetMap.get(targetId) : null;

  // Aggregate severity totals (open vulns only)
  const sevTotals: Record<(typeof SEV_ORDER)[number], number> = {
    critical: 0, high: 0, medium: 0, low: 0, info: 0,
  };
  vulns.data?.forEach((v) => {
    if (!TERMINAL_STATES.has(v.state) && v.severity in sevTotals) {
      sevTotals[v.severity]++;
    }
  });

  const overdueCount = vulns.data?.filter(
    (v) =>
      v.sla_due_at &&
      new Date(v.sla_due_at) < new Date() &&
      !TERMINAL_STATES.has(v.state),
  ).length ?? 0;

  const completedCount = scans.data?.filter((s) => s.status === "completed").length ?? 0;
  const runningCount = scans.data?.filter((s) => s.status === "running" || s.status === "queued").length ?? 0;
  const totalFindings = scans.data?.reduce(
    (sum, s) =>
      sum +
      Object.values(s.summary || {}).reduce(
        (a: number, b) => a + Number(b ?? 0),
        0,
      ),
    0,
  ) ?? 0;

  // Build a per-day scan-volume time series for the last 14 days
  const days = 14;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const buckets: number[] = new Array(days).fill(0);
  scans.data?.forEach((s) => {
    const d = new Date(s.created_at);
    d.setHours(0, 0, 0, 0);
    const diff = Math.floor((today.getTime() - d.getTime()) / 86_400_000);
    if (diff >= 0 && diff < days) buckets[days - 1 - diff]++;
  });

  // Top vulnerable targets — only meaningful when not already target-filtered
  const byTarget = new Map<string, number>();
  vulns.data?.forEach((v) => {
    if (TERMINAL_STATES.has(v.state)) return;
    byTarget.set(v.target_id, (byTarget.get(v.target_id) ?? 0) + 1);
  });
  const topTargets = Array.from(byTarget.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const recentScans = (scans.data ?? []).slice(0, 6);

  // Total project count is global, not filtered (shows org-wide footprint)
  const projectCount = projects.data?.length ?? 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description={
          selectedTarget
            ? `Scoped to ${selectedTarget.name}`
            : "Continuous overview of your DAST posture across all projects."
        }
        action={
          isFiltered && (
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => {
                setProjectId("");
                setTargetId("");
              }}
            >
              Reset filters
            </button>
          )
        }
      />

      {/* Filter bar */}
      <div className="card p-3">
        <TargetFilter
          projectId={projectId}
          onProjectChange={(id) => {
            setProjectId(id);
            // Clearing project clears target if it doesn't belong
            if (
              id &&
              targetId &&
              targetMap.get(targetId)?.project_id !== id
            ) {
              setTargetId("");
            }
          }}
          value={targetId}
          onChange={setTargetId}
        />
        {selectedTarget && (
          <p className="mt-2 flex items-center gap-1 text-[11px] text-slate-500">
            <ExternalLink className="h-3 w-3" />
            <a
              href={selectedTarget.base_url}
              target="_blank"
              rel="noopener"
              className="font-mono hover:text-accent"
            >
              {selectedTarget.base_url}
            </a>
          </p>
        )}
      </div>

      {anyError && (
        <p className="text-sm text-severity-critical">
          {(scans.error ?? vulns.error ?? projects.error) instanceof ApiError
            ? (scans.error ?? vulns.error ?? projects.error)?.message
            : "Error loading dashboard"}
        </p>
      )}

      {/* Stat cards */}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={FolderKanban}
          label="Projects"
          value={projectCount}
          href="/projects"
          loading={loading}
          dimmedWhenFiltered={isFiltered}
        />
        <StatCard
          icon={ScanLine}
          label={selectedTarget ? "Scans (this target)" : "Scans"}
          sub={`${runningCount} active · ${completedCount} completed`}
          value={scans.data?.length ?? 0}
          href={`/scans${targetId || projectId ? "" : ""}`}
          loading={loading}
          spark={buckets}
        />
        <StatCard
          icon={Bug}
          label={selectedTarget ? "Open vulns (this target)" : "Open vulnerabilities"}
          value={vulns.data?.filter((v) => !TERMINAL_STATES.has(v.state)).length ?? 0}
          href="/vulnerabilities"
          loading={loading}
        />
        <StatCard
          icon={AlertTriangle}
          label="SLA overdue"
          value={overdueCount}
          tone={overdueCount > 0 ? "text-severity-critical" : undefined}
          href="/vulnerabilities"
          loading={loading}
        />
      </div>

      {/* Severity + scan volume */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="card md:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="section-title">
              {selectedTarget
                ? `Open vulnerabilities · ${selectedTarget.name}`
                : "Open vulnerabilities by severity"}
            </h2>
            <span className="text-xs text-slate-500">
              {totalFindings} findings ingested across these scans
            </span>
          </div>
          {loading ? (
            <div className="space-y-3">
              {SEV_ORDER.map((s) => (
                <Skeleton key={s} className="h-6" />
              ))}
            </div>
          ) : (
            <HBarChart
              data={SEV_ORDER.map((s) => ({
                label: s,
                value: sevTotals[s],
                color: `bg-severity-${s}`,
              }))}
            />
          )}
        </div>

        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="section-title">Scan volume · 14d</h2>
            <span className="text-xs text-slate-500">
              {buckets.reduce((a, b) => a + b, 0)} runs
            </span>
          </div>
          <div className="flex items-end justify-center py-3">
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <Sparkline values={buckets} width={260} height={70} />
            )}
          </div>
          <p className="text-[11px] text-slate-500">
            One point per day · last 14 days
          </p>
        </div>
      </div>

      {/* Recent scans + top targets */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="card md:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="section-title">
              {selectedTarget ? "Recent scans · this target" : "Recent scans"}
            </h2>
            <Link
              href="/scans"
              className="text-xs text-accent hover:underline"
            >
              View all →
            </Link>
          </div>
          <div className="overflow-hidden rounded-md">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  {!selectedTarget && <th>Target</th>}
                  <th>Engine</th>
                  <th>Status</th>
                  <th className="text-right">Findings</th>
                </tr>
              </thead>
              <tbody>
                {loading &&
                  Array.from({ length: 3 }).map((_, i) => (
                    <tr key={i}>
                      <td colSpan={selectedTarget ? 4 : 5} className="py-2">
                        <Skeleton className="h-4 w-full" />
                      </td>
                    </tr>
                  ))}
                {!loading && recentScans.length === 0 && (
                  <tr>
                    <td
                      colSpan={selectedTarget ? 4 : 5}
                      className="py-8 text-center text-sm text-slate-500"
                    >
                      No scans match this filter — head over to{" "}
                      <Link href="/scans" className="text-accent">Scans</Link>{" "}
                      to start one.
                    </td>
                  </tr>
                )}
                {!loading &&
                  recentScans.map((s) => {
                    const total = Object.values(s.summary || {}).reduce(
                      (a, b) => a + Number(b ?? 0),
                      0,
                    );
                    const t = targetMap.get(s.target_id);
                    return (
                      <tr key={s.id}>
                        <td>
                          <Link
                            href={`/scans/${s.id}`}
                            className="text-slate-200 hover:text-accent"
                          >
                            {new Date(s.created_at).toLocaleString()}
                          </Link>
                        </td>
                        {!selectedTarget && (
                          <td className="max-w-[180px] truncate text-xs">
                            {t ? (
                              <span className="text-slate-200">{t.name}</span>
                            ) : (
                              <span className="font-mono text-slate-500">
                                {s.target_id.slice(0, 8)}…
                              </span>
                            )}
                          </td>
                        )}
                        <td>
                          <EngineBadge engine={s.engine} />
                        </td>
                        <td>
                          <StatusPill status={s.status} />
                        </td>
                        <td className="text-right text-xs">
                          {total > 0 ? (
                            <span className="font-mono text-slate-200">
                              {total}
                            </span>
                          ) : (
                            <span className="text-slate-500">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="section-title">
              {selectedTarget ? "About this target" : "Top vulnerable targets"}
            </h2>
            <TargetIcon className="h-4 w-4 text-slate-500" />
          </div>
          {selectedTarget ? (
            <dl className="space-y-2 text-sm">
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  Name
                </dt>
                <dd className="text-slate-200">{selectedTarget.name}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  Base URL
                </dt>
                <dd className="break-all font-mono text-xs">
                  <a
                    href={selectedTarget.base_url}
                    target="_blank"
                    rel="noopener"
                    className="text-accent hover:underline"
                  >
                    {selectedTarget.base_url}
                  </a>
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  Total scans
                </dt>
                <dd className="text-slate-200">{scans.data?.length ?? 0}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-wide text-slate-500">
                  Open vulnerabilities
                </dt>
                <dd className="text-slate-200">
                  {vulns.data?.filter((v) => !TERMINAL_STATES.has(v.state))
                    .length ?? 0}
                </dd>
              </div>
            </dl>
          ) : loading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-6" />
              ))}
            </div>
          ) : topTargets.length === 0 ? (
            <p className="py-6 text-center text-xs text-slate-500">
              No open vulnerabilities yet
            </p>
          ) : (
            <ul className="space-y-2">
              {topTargets.map(([tid, count]) => {
                const t = targetMap.get(tid);
                return (
                  <li
                    key={tid}
                    className="flex items-center justify-between gap-2 rounded-md bg-bg/40 px-3 py-2 text-sm"
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left transition hover:text-accent"
                      onClick={() => setTargetId(tid)}
                      title="Filter dashboard to this target"
                    >
                      <div className="truncate text-slate-200">
                        {t?.name ?? `${tid.slice(0, 8)}…`}
                      </div>
                      {t && (
                        <div className="truncate font-mono text-[10px] text-slate-500">
                          {t.base_url}
                        </div>
                      )}
                    </button>
                    <span className="badge bg-severity-critical/15 text-severity-critical">
                      {count}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
  href,
  tone,
  loading,
  spark,
  dimmedWhenFiltered,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  sub?: string;
  href: string;
  tone?: string;
  loading?: boolean;
  spark?: number[];
  dimmedWhenFiltered?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`card card-hover block ${dimmedWhenFiltered ? "opacity-60" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            <Icon className="h-3.5 w-3.5" />
            {label}
          </div>
          {loading ? (
            <Skeleton className="mt-2 h-8 w-20" />
          ) : (
            <div className={`mt-1 text-3xl font-bold ${tone ?? "text-slate-100"}`}>
              {value}
            </div>
          )}
          {sub && (
            <p className="mt-1 text-[11px] text-slate-500">{sub}</p>
          )}
        </div>
        {spark && spark.length > 0 && !loading && (
          <Sparkline values={spark} width={64} height={28} />
        )}
      </div>
    </Link>
  );
}
