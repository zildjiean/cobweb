"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AlertTriangle, Bug, ExternalLink, Search } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import FindingDetailModal, {
  FindingDetail,
} from "@/components/FindingDetailModal";
import { SeverityPill } from "@/components/ui/Badges";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";
import { TargetFilter } from "@/components/ui/TargetFilter";

interface Vuln {
  id: string;
  project_id: string;
  target_id: string;
  template_id: string;
  name: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  state:
    | "new"
    | "triaged"
    | "in_progress"
    | "resolved"
    | "verified"
    | "false_positive"
    | "accepted_risk"
    | "regression";
  sla_due_at: string | null;
  last_seen_at: string | null;
  notes: string | null;
}

interface Target {
  id: string;
  name: string;
  base_url: string;
  project_id: string;
}

const COLUMNS: { key: Vuln["state"]; label: string; tone: string }[] = [
  { key: "new", label: "New", tone: "from-slate-700/40 to-transparent" },
  { key: "triaged", label: "Triaged", tone: "from-amber-500/20 to-transparent" },
  { key: "in_progress", label: "In progress", tone: "from-accent/20 to-transparent" },
  { key: "resolved", label: "Resolved", tone: "from-emerald-500/20 to-transparent" },
  { key: "verified", label: "Verified", tone: "from-emerald-700/30 to-transparent" },
  { key: "regression", label: "Regression", tone: "from-severity-critical/25 to-transparent" },
];

const NEXT_STATE: Partial<Record<Vuln["state"], Vuln["state"]>> = {
  new: "triaged",
  triaged: "in_progress",
  in_progress: "resolved",
  resolved: "verified",
  regression: "in_progress",
};

const SEV_ORDER: Vuln["severity"][] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
];

export default function VulnPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [filterSev, setFilterSev] = useState<string>("");
  const [filterProject, setFilterProject] = useState<string>("");
  const [filterTarget, setFilterTarget] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [activeFinding, setActiveFinding] = useState<{
    scanId: string;
    findingId: string;
  } | null>(null);

  async function openLatestFinding(vulnId: string) {
    try {
      const list = await api<FindingDetail[]>(
        `/api/v1/vulnerabilities/${vulnId}/findings`,
      );
      if (list.length === 0) {
        toast.push({
          kind: "warning",
          title: "No findings linked yet",
          description: "Wait for the next scan to populate this vulnerability.",
        });
        return;
      }
      const latest = list[0];
      setActiveFinding({ scanId: latest.scan_id, findingId: latest.id });
    } catch (e) {
      toast.push({
        kind: "error",
        title: "Failed to load finding",
        description: e instanceof ApiError ? e.message : undefined,
      });
    }
  }

  const vulns = useQuery({
    queryKey: ["vulnerabilities", filterSev, filterProject, filterTarget],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (filterSev) qs.set("severity", filterSev);
      if (filterProject) qs.set("project_id", filterProject);
      if (filterTarget) qs.set("target_id", filterTarget);
      return api<Vuln[]>(
        `/api/v1/vulnerabilities${qs.toString() ? `?${qs}` : ""}`,
      );
    },
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

  const transition = useMutation({
    mutationFn: ({
      id,
      state,
      notes,
      accepted_until,
    }: {
      id: string;
      state: Vuln["state"];
      notes?: string;
      accepted_until?: string;
    }) =>
      api(`/api/v1/vulnerabilities/${id}/transition`, {
        method: "POST",
        body: JSON.stringify({ state, notes, accepted_until }),
      }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["vulnerabilities"] });
      toast.push({
        kind: "success",
        title: `Moved to ${vars.state.replace(/_/g, " ")}`,
      });
    },
    onError: (err) => {
      toast.push({
        kind: "error",
        title: "Transition failed",
        description: err instanceof ApiError ? err.message : undefined,
      });
    },
  });

  const filteredVulns = (vulns.data ?? []).filter((v) => {
    if (!search) return true;
    const t = targetMap.get(v.target_id);
    return [v.name, v.template_id, t?.name ?? "", t?.base_url ?? ""]
      .join(" ")
      .toLowerCase()
      .includes(search.toLowerCase());
  });

  const grouped: Record<Vuln["state"], Vuln[]> = {
    new: [],
    triaged: [],
    in_progress: [],
    resolved: [],
    verified: [],
    false_positive: [],
    accepted_risk: [],
    regression: [],
  };
  filteredVulns.forEach((v) => grouped[v.state].push(v));
  for (const k of Object.keys(grouped) as Vuln["state"][]) {
    grouped[k].sort(
      (a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity),
    );
  }

  // Quick stats
  const TERMINAL = new Set(["false_positive", "accepted_risk", "verified"]);
  const open = filteredVulns.filter((v) => !TERMINAL.has(v.state));
  const overdue = open.filter(
    (v) => v.sla_due_at && new Date(v.sla_due_at) < new Date(),
  ).length;

  const selectedTarget = filterTarget ? targetMap.get(filterTarget) : null;
  const isFiltered =
    !!filterSev || !!filterProject || !!filterTarget || !!search;

  return (
    <div>
      <PageHeader
        title="Vulnerabilities"
        description={
          selectedTarget
            ? `Scoped to ${selectedTarget.name}`
            : "Lifecycle board · drag-style triage workflow."
        }
        action={
          isFiltered && (
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => {
                setFilterSev("");
                setFilterProject("");
                setFilterTarget("");
                setSearch("");
              }}
            >
              Reset filters
            </button>
          )
        }
      />

      {/* Target / project filter */}
      <div className="card mb-3 p-3">
        <TargetFilter
          projectId={filterProject}
          onProjectChange={(id) => {
            setFilterProject(id);
            if (
              id &&
              filterTarget &&
              targetMap.get(filterTarget)?.project_id !== id
            ) {
              setFilterTarget("");
            }
          }}
          value={filterTarget}
          onChange={setFilterTarget}
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

      {/* Quick stats */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Open" value={open.length} />
        <Stat
          label="Overdue (SLA)"
          value={overdue}
          tone={overdue > 0 ? "text-severity-critical" : undefined}
        />
        <Stat
          label="Resolved"
          value={grouped.resolved.length + grouped.verified.length}
          tone="text-emerald-300"
        />
        <Stat
          label="False positive"
          value={grouped.false_positive.length}
          tone="text-slate-300"
        />
      </div>

      {/* Filter bar */}
      <div className="card mb-4 flex flex-wrap items-center gap-2 p-2.5">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
          <input
            className="input !pl-8"
            placeholder="Search by name, template, target…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="input w-auto"
          value={filterSev}
          onChange={(e) => setFilterSev(e.target.value)}
        >
          <option value="">All severities</option>
          {SEV_ORDER.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {vulns.isLoading && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      )}
      {vulns.error && (
        <p className="text-severity-critical">
          {vulns.error instanceof ApiError ? vulns.error.message : "Error"}
        </p>
      )}

      {!vulns.isLoading && filteredVulns.length === 0 && (
        <div className="card">
          <EmptyState
            icon={Bug}
            title="No vulnerabilities match"
            description={
              search || filterSev
                ? "Try clearing filters."
                : "Run a scan to start collecting findings."
            }
          />
        </div>
      )}

      {!vulns.isLoading && filteredVulns.length > 0 && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {COLUMNS.map((col) => (
            <div
              key={col.key}
              className="overflow-hidden rounded-lg border border-border-subtle bg-bg-elevated"
            >
              <div
                className={`flex items-center justify-between bg-gradient-to-b px-3 py-2 ${col.tone}`}
              >
                <span className="text-xs font-semibold tracking-wide text-slate-200">
                  {col.label}
                </span>
                <span className="badge bg-bg/60 text-slate-300">
                  {grouped[col.key].length}
                </span>
              </div>
              <div className="space-y-2 p-2">
                {grouped[col.key].map((v) => {
                  const next = NEXT_STATE[v.state];
                  const target = targetMap.get(v.target_id);
                  const overdueCard =
                    v.sla_due_at && new Date(v.sla_due_at) < new Date();
                  return (
                    <div
                      key={v.id}
                      className="rounded-md border border-border-subtle bg-bg-subtle p-2.5 text-sm transition hover:border-border"
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <SeverityPill severity={v.severity} size="xs" />
                        {overdueCard && (
                          <span
                            className="badge bg-severity-critical/15 text-severity-critical"
                            title="SLA overdue"
                          >
                            <AlertTriangle className="h-3 w-3" />
                            overdue
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        className="block w-full text-left font-medium leading-tight text-slate-100 hover:text-accent"
                        onClick={() => openLatestFinding(v.id)}
                        title="Click for full request / response / payload"
                      >
                        {v.name}
                      </button>
                      <div className="mt-1 truncate font-mono text-[10px] text-slate-500">
                        {v.template_id}
                      </div>
                      {target && (
                        <div className="mt-1 truncate text-[11px] text-slate-400">
                          {target.name}
                        </div>
                      )}
                      <div className="mt-2 flex flex-wrap gap-1">
                        {next && (
                          <button
                            className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent transition hover:bg-accent/25"
                            onClick={() =>
                              transition.mutate({ id: v.id, state: next })
                            }
                          >
                            → {next.replace(/_/g, " ")}
                          </button>
                        )}
                        {v.state !== "false_positive" && (
                          <button
                            className="rounded bg-bg/80 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-bg"
                            onClick={() =>
                              transition.mutate({
                                id: v.id,
                                state: "false_positive",
                              })
                            }
                          >
                            FP
                          </button>
                        )}
                        {(v.state === "new" ||
                          v.state === "triaged" ||
                          v.state === "in_progress") && (
                          <button
                            className="rounded bg-bg/80 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-bg"
                            onClick={() => {
                              const until = window.prompt(
                                "Accept until (YYYY-MM-DD):",
                                "2027-01-01",
                              );
                              if (until)
                                transition.mutate({
                                  id: v.id,
                                  state: "accepted_risk",
                                  accepted_until: `${until}T00:00:00Z`,
                                });
                            }}
                          >
                            Accept
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
                {grouped[col.key].length === 0 && (
                  <p className="px-2 py-3 text-center text-[11px] text-slate-600">
                    —
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Side states (FP / Accepted Risk) */}
      {!vulns.isLoading &&
        (grouped.false_positive.length > 0 ||
          grouped.accepted_risk.length > 0) && (
          <div className="mt-5 grid gap-3 md:grid-cols-2">
            {(["false_positive", "accepted_risk"] as const).map((k) => (
              <div key={k} className="card">
                <h3 className="section-title mb-2">
                  {k.replace(/_/g, " ")} · {grouped[k].length}
                </h3>
                <ul className="space-y-1 text-sm">
                  {grouped[k].map((v) => (
                    <li
                      key={v.id}
                      className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-bg/40"
                    >
                      <SeverityPill severity={v.severity} size="xs" />
                      <button
                        className="flex-1 truncate text-left text-slate-200 hover:text-accent"
                        onClick={() => openLatestFinding(v.id)}
                      >
                        {v.name}
                      </button>
                      <span className="font-mono text-xs text-slate-500">
                        {v.template_id}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

      {activeFinding && (
        <FindingDetailModal
          scanId={activeFinding.scanId}
          findingId={activeFinding.findingId}
          onClose={() => setActiveFinding(null)}
        />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: string;
}) {
  return (
    <div className="card p-3">
      <div className={`text-2xl font-bold ${tone ?? "text-slate-100"}`}>
        {value}
      </div>
      <div className="text-[11px] uppercase tracking-wide text-slate-400">
        {label}
      </div>
    </div>
  );
}
