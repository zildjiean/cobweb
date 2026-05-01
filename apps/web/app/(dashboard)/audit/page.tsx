"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ChevronDown, ChevronRight, History, Search } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";

interface AuditEntry {
  id: number;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  ip: string | null;
  user_agent: string | null;
  payload: Record<string, unknown>;
  hash: string;
  prev_hash: string | null;
  created_at: string;
}

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const logs = useQuery({
    queryKey: ["audit", action, resourceType],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (action) qs.set("action", action);
      if (resourceType) qs.set("resource_type", resourceType);
      return api<AuditEntry[]>(
        `/api/v1/audit-logs${qs.toString() ? `?${qs}` : ""}`,
      );
    },
  });

  function toggleExpand(id: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div>
      <PageHeader
        title="Audit log"
        description="Append-only, hash-chained record of every mutating action."
      />

      <div className="card mb-3 flex flex-wrap items-center gap-2 p-2.5">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
          <input
            className="input !pl-8"
            placeholder="action (e.g. project.create)"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
        </div>
        <input
          className="input flex-1 min-w-[200px]"
          placeholder="resource_type (e.g. scan)"
          value={resourceType}
          onChange={(e) => setResourceType(e.target.value)}
        />
        {(action || resourceType) && (
          <button
            className="btn-ghost text-xs"
            onClick={() => {
              setAction("");
              setResourceType("");
            }}
          >
            Clear
          </button>
        )}
      </div>

      {logs.isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-8" />
          ))}
        </div>
      )}
      {logs.error && (
        <p className="text-severity-critical">
          {logs.error instanceof ApiError ? logs.error.message : "Error"}
        </p>
      )}

      <div className="card overflow-hidden p-0">
        <table className="table">
          <thead>
            <tr>
              <th className="w-8"></th>
              <th>When</th>
              <th>Actor</th>
              <th>Action</th>
              <th>Resource</th>
              <th>Hash</th>
            </tr>
          </thead>
          <tbody>
            {!logs.isLoading &&
              logs.data?.map((e) => {
                const isExpanded = expanded.has(e.id);
                const hasPayload = Object.keys(e.payload || {}).length > 0;
                return (
                  <>
                    <tr
                      key={e.id}
                      onClick={() => hasPayload && toggleExpand(e.id)}
                      className={hasPayload ? "cursor-pointer" : ""}
                    >
                      <td>
                        {hasPayload ? (
                          isExpanded ? (
                            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                          ) : (
                            <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                          )
                        ) : null}
                      </td>
                      <td className="whitespace-nowrap font-mono text-xs">
                        {new Date(e.created_at).toLocaleString()}
                      </td>
                      <td className="font-mono text-xs">
                        {e.actor_id ? e.actor_id.slice(0, 8) : "—"}
                      </td>
                      <td>
                        <span className="font-mono text-xs text-accent">
                          {e.action}
                        </span>
                      </td>
                      <td className="font-mono text-xs">
                        {e.resource_type}
                        {e.resource_id ? `:${e.resource_id.slice(0, 8)}` : ""}
                      </td>
                      <td
                        className="font-mono text-[10px] text-slate-500"
                        title={e.hash}
                      >
                        {e.hash.slice(0, 12)}…
                      </td>
                    </tr>
                    {isExpanded && hasPayload && (
                      <tr className="bg-bg/30">
                        <td colSpan={6}>
                          <pre className="overflow-x-auto rounded bg-bg/60 p-2 font-mono text-[11px] text-slate-300">
                            {JSON.stringify(e.payload, null, 2)}
                          </pre>
                          <p className="mt-1.5 text-[10px] text-slate-500">
                            ip: {e.ip ?? "—"} · ua:{" "}
                            {e.user_agent ? e.user_agent.slice(0, 80) : "—"}
                          </p>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            {!logs.isLoading && logs.data?.length === 0 && (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon={History}
                    title="No matching entries"
                    description="Adjust the filters above to broaden your search."
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] text-slate-500">
        Each entry includes a hash of the previous one, forming a tamper-evident
        chain. Total {logs.data?.length ?? 0} entries shown.
      </p>
    </div>
  );
}
