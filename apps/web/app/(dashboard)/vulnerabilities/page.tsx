"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bug,
  ExternalLink,
  EyeOff,
  Search,
  Shield,
  X,
} from "lucide-react";
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

interface Suppression {
  id: string;
  target_id: string;
  dedupe_hash: string;
  reason: string | null;
  created_by: string | null;
  expires_at: string;
  created_at: string;
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

type MinSev = Vuln["severity"] | "all";
const MIN_SEV_KEY = "cobweb.vuln.minSeverity";
const GROUP_KEY = "cobweb.vuln.groupByTemplate";

function severityAtLeast(v: Vuln["severity"], floor: MinSev): boolean {
  if (floor === "all") return true;
  return SEV_ORDER.indexOf(v) <= SEV_ORDER.indexOf(floor);
}

function highestSeverity(items: Vuln[]): Vuln["severity"] {
  let best = SEV_ORDER.length - 1;
  for (const v of items) {
    const i = SEV_ORDER.indexOf(v.severity);
    if (i < best) best = i;
  }
  return SEV_ORDER[best];
}

interface VulnGroup {
  key: string; // target_id::template_id
  target_id: string;
  template_id: string;
  name: string;
  severity: Vuln["severity"];
  members: Vuln[]; // members within a single state column
}

function groupByTemplate(items: Vuln[]): VulnGroup[] {
  const map = new Map<string, Vuln[]>();
  for (const v of items) {
    const k = `${v.target_id}::${v.template_id}`;
    const arr = map.get(k);
    if (arr) arr.push(v);
    else map.set(k, [v]);
  }
  const out: VulnGroup[] = [];
  for (const [k, members] of map) {
    out.push({
      key: k,
      target_id: members[0].target_id,
      template_id: members[0].template_id,
      name: members[0].name,
      severity: highestSeverity(members),
      members,
    });
  }
  out.sort(
    (a, b) =>
      SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity) ||
      b.members.length - a.members.length,
  );
  return out;
}

export default function VulnPage() {
  const qc = useQueryClient();
  const toast = useToast();

  const [minSev, setMinSev] = useState<MinSev>("medium");
  const [grouping, setGrouping] = useState<boolean>(true);
  const [filterProject, setFilterProject] = useState<string>("");
  const [filterTarget, setFilterTarget] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [showSuppressed, setShowSuppressed] = useState(false);
  const [activeFinding, setActiveFinding] = useState<{
    scanId: string;
    findingId: string;
  } | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  // Load persisted prefs.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const s = window.localStorage.getItem(MIN_SEV_KEY);
    if (s && (SEV_ORDER as string[]).concat("all").includes(s)) {
      setMinSev(s as MinSev);
    }
    const g = window.localStorage.getItem(GROUP_KEY);
    if (g === "0") setGrouping(false);
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined")
      window.localStorage.setItem(MIN_SEV_KEY, minSev);
  }, [minSev]);

  useEffect(() => {
    if (typeof window !== "undefined")
      window.localStorage.setItem(GROUP_KEY, grouping ? "1" : "0");
  }, [grouping]);

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
    queryKey: ["vulnerabilities", filterProject, filterTarget],
    queryFn: () => {
      const qs = new URLSearchParams();
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
      qc.invalidateQueries({ queryKey: ["suppressions"] });
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

  const bulkTransition = useMutation({
    mutationFn: async (vars: {
      ids: string[];
      state: Vuln["state"];
      accepted_until?: string;
    }) => {
      const results = await Promise.allSettled(
        vars.ids.map((id) =>
          api(`/api/v1/vulnerabilities/${id}/transition`, {
            method: "POST",
            body: JSON.stringify({
              state: vars.state,
              accepted_until: vars.accepted_until,
            }),
          }),
        ),
      );
      const ok = results.filter((r) => r.status === "fulfilled").length;
      const fail = results.length - ok;
      return { ok, fail };
    },
    onSuccess: ({ ok, fail }, vars) => {
      qc.invalidateQueries({ queryKey: ["vulnerabilities"] });
      qc.invalidateQueries({ queryKey: ["suppressions"] });
      if (fail === 0) {
        toast.push({
          kind: "success",
          title: `Moved ${ok} → ${vars.state.replace(/_/g, " ")}`,
        });
      } else {
        toast.push({
          kind: "warning",
          title: `Moved ${ok}/${ok + fail}`,
          description: `${fail} could not transition (state machine).`,
        });
      }
    },
  });

  const filteredVulns = (vulns.data ?? []).filter((v) => {
    if (!severityAtLeast(v.severity, minSev)) return false;
    if (search) {
      const t = targetMap.get(v.target_id);
      const hay = [v.name, v.template_id, t?.name ?? "", t?.base_url ?? ""]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(search.toLowerCase())) return false;
    }
    return true;
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
    minSev !== "medium" ||
    !!filterProject ||
    !!filterTarget ||
    !!search ||
    !grouping;

  function toggleExpand(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

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
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => setShowSuppressed(true)}
              title="Manage auto-FP suppressions"
            >
              <EyeOff className="h-4 w-4" />
              Suppressed
            </button>
            {isFiltered && (
              <button
                type="button"
                className="btn-ghost text-sm"
                onClick={() => {
                  setMinSev("medium");
                  setFilterProject("");
                  setFilterTarget("");
                  setSearch("");
                  setGrouping(true);
                }}
              >
                Reset filters
              </button>
            )}
          </div>
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
        <label
          className="flex items-center gap-1.5 text-xs text-slate-400"
          title="Hide findings below this severity"
        >
          <Shield className="h-3.5 w-3.5" />
          Min severity
        </label>
        <select
          className="input w-auto"
          value={minSev}
          onChange={(e) => setMinSev(e.target.value as MinSev)}
        >
          {SEV_ORDER.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
          <option value="all">show all</option>
        </select>
        <label className="flex items-center gap-1.5 text-xs text-slate-400">
          <input
            type="checkbox"
            className="accent-accent"
            checked={grouping}
            onChange={(e) => setGrouping(e.target.checked)}
          />
          Group by template
        </label>
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
              search || minSev !== "all"
                ? "Try lowering Min severity or clearing filters."
                : "Run a scan to start collecting findings."
            }
          />
        </div>
      )}

      {!vulns.isLoading && filteredVulns.length > 0 && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {COLUMNS.map((col) => {
            const colItems = grouped[col.key];
            const next = NEXT_STATE[col.key];
            return (
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
                    {colItems.length}
                  </span>
                </div>
                <div className="space-y-2 p-2">
                  {grouping
                    ? groupByTemplate(colItems).map((g) => {
                        const target = targetMap.get(g.target_id);
                        const isExp = expanded.has(`${col.key}|${g.key}`);
                        const ids = g.members.map((m) => m.id);
                        const anyOverdue = g.members.some(
                          (m) =>
                            m.sla_due_at &&
                            new Date(m.sla_due_at) < new Date(),
                        );
                        return (
                          <div
                            key={g.key}
                            className="rounded-md border border-border-subtle bg-bg-subtle p-2.5 text-sm"
                          >
                            <div className="mb-1.5 flex items-center justify-between gap-2">
                              <SeverityPill severity={g.severity} size="xs" />
                              <div className="flex items-center gap-1">
                                {anyOverdue && (
                                  <span
                                    className="badge bg-severity-critical/15 text-severity-critical"
                                    title="One or more members SLA overdue"
                                  >
                                    <AlertTriangle className="h-3 w-3" />
                                    overdue
                                  </span>
                                )}
                                {g.members.length > 1 && (
                                  <span
                                    className="badge bg-bg/60 text-slate-300"
                                    title={`${g.members.length} occurrences`}
                                  >
                                    ×{g.members.length}
                                  </span>
                                )}
                              </div>
                            </div>
                            <button
                              type="button"
                              className="block w-full text-left font-medium leading-tight text-slate-100 hover:text-accent"
                              onClick={() =>
                                g.members.length === 1
                                  ? openLatestFinding(g.members[0].id)
                                  : toggleExpand(`${col.key}|${g.key}`)
                              }
                              title={
                                g.members.length === 1
                                  ? "Open finding"
                                  : "Expand occurrences"
                              }
                            >
                              {g.name}
                            </button>
                            <div className="mt-1 truncate font-mono text-[10px] text-slate-500">
                              {g.template_id}
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
                                    bulkTransition.mutate({
                                      ids,
                                      state: next,
                                    })
                                  }
                                  title={`Move all ${ids.length}`}
                                >
                                  → {next.replace(/_/g, " ")}
                                </button>
                              )}
                              {col.key !== "false_positive" && (
                                <button
                                  className="rounded bg-bg/80 px-1.5 py-0.5 text-[10px] text-slate-300 hover:bg-bg"
                                  onClick={() =>
                                    bulkTransition.mutate({
                                      ids,
                                      state: "false_positive",
                                    })
                                  }
                                  title={`Mark ${ids.length} as false positive (auto-suppress)`}
                                >
                                  FP
                                </button>
                              )}
                            </div>
                            {isExp && g.members.length > 1 && (
                              <ul className="mt-2 space-y-1 border-t border-border-subtle/60 pt-2">
                                {g.members.map((m) => (
                                  <li
                                    key={m.id}
                                    className="flex items-center gap-1.5 text-[11px] text-slate-400"
                                  >
                                    <button
                                      className="flex-1 truncate text-left hover:text-accent"
                                      onClick={() => openLatestFinding(m.id)}
                                    >
                                      {m.id.slice(0, 8)}
                                    </button>
                                    {m.state !== "false_positive" && (
                                      <button
                                        className="rounded bg-bg/80 px-1 py-px text-[9px] hover:bg-bg"
                                        onClick={() =>
                                          transition.mutate({
                                            id: m.id,
                                            state: "false_positive",
                                          })
                                        }
                                      >
                                        FP
                                      </button>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        );
                      })
                    : colItems.map((v) => {
                        const nx = NEXT_STATE[v.state];
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
                              {nx && (
                                <button
                                  className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] text-accent transition hover:bg-accent/25"
                                  onClick={() =>
                                    transition.mutate({ id: v.id, state: nx })
                                  }
                                >
                                  → {nx.replace(/_/g, " ")}
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
                  {colItems.length === 0 && (
                    <p className="px-2 py-3 text-center text-[11px] text-slate-600">
                      —
                    </p>
                  )}
                </div>
              </div>
            );
          })}
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

      {showSuppressed && (
        <SuppressionsDrawer
          targetMap={targetMap}
          onClose={() => setShowSuppressed(false)}
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

function SuppressionsDrawer({
  targetMap,
  onClose,
}: {
  targetMap: Map<string, Target>;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();

  const sup = useQuery({
    queryKey: ["suppressions"],
    queryFn: () => api<Suppression[]>("/api/v1/suppressions"),
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/api/v1/suppressions/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["suppressions"] });
      qc.invalidateQueries({ queryKey: ["vulnerabilities"] });
      toast.push({
        kind: "success",
        title: "Suppression removed",
        description: "Affected vulnerabilities reverted to NEW.",
      });
    },
    onError: (e) =>
      toast.push({
        kind: "error",
        title: "Un-suppress failed",
        description: e instanceof ApiError ? e.message : undefined,
      }),
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/60"
      onClick={onClose}
    >
      <div
        className="flex h-full w-full max-w-md flex-col bg-bg-elevated shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-100">
            Auto-FP suppressions
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-bg/60 hover:text-slate-100"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-auto p-3">
          {sup.isLoading && <Skeleton className="h-24" />}
          {sup.error && (
            <p className="text-severity-critical">
              {sup.error instanceof ApiError ? sup.error.message : "Error"}
            </p>
          )}
          {sup.data && sup.data.length === 0 && (
            <EmptyState
              icon={EyeOff}
              title="No active suppressions"
              description="Marking a vulnerability as False Positive will create one here."
            />
          )}
          {sup.data && sup.data.length > 0 && (
            <ul className="space-y-2">
              {sup.data.map((s) => {
                const t = targetMap.get(s.target_id);
                const exp = new Date(s.expires_at);
                const expDays = Math.round(
                  (exp.getTime() - Date.now()) / (1000 * 60 * 60 * 24),
                );
                return (
                  <li
                    key={s.id}
                    className="rounded-md border border-border-subtle bg-bg-subtle p-2.5 text-sm"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium text-slate-100">
                          {t?.name ?? "(unknown target)"}
                        </div>
                        <div className="truncate font-mono text-[10px] text-slate-500">
                          {s.dedupe_hash.slice(0, 16)}…
                        </div>
                        {s.reason && (
                          <p className="mt-1 line-clamp-2 text-[11px] text-slate-400">
                            {s.reason}
                          </p>
                        )}
                        <p className="mt-1 text-[11px] text-slate-500">
                          expires in {expDays}d
                        </p>
                      </div>
                      <button
                        type="button"
                        className="rounded bg-bg/80 px-2 py-1 text-[11px] text-slate-200 hover:bg-bg"
                        onClick={() => remove.mutate(s.id)}
                        disabled={remove.isPending}
                      >
                        Un-suppress
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <div className="border-t border-border-subtle px-4 py-2 text-[11px] text-slate-500">
          Un-suppress reverts the matching vulnerability back to NEW.
        </div>
      </div>
    </div>
  );
}
