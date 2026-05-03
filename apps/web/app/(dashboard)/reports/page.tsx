"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Download, FileBarChart2, FileText } from "lucide-react";
import { api, API_BASE, ApiError, tokenStore } from "@/lib/api";
import { StatusPill } from "@/components/ui/Badges";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";

interface Scan {
  id: string;
  target_id: string;
  status: string;
  engine: string;
  summary: Record<string, number>;
  finished_at: string | null;
  created_at: string;
}

interface Target {
  id: string;
  name: string;
  base_url: string;
}

const TEMPLATES = [
  {
    kind: "executive",
    label: "Executive summary",
    desc: "1-page overview suitable for leadership",
  },
  {
    kind: "technical",
    label: "Technical detail",
    desc: "Per-finding breakdown with payloads",
  },
  {
    kind: "owasp",
    label: "OWASP Top 10",
    desc: "Findings mapped to OWASP categories",
  },
  {
    kind: "pci_dss",
    label: "PCI-DSS Req 6.5",
    desc: "Compliance mapping for PCI-DSS",
  },
  {
    kind: "iso27001",
    label: "ISO 27001 Annex A",
    desc: "Mapped to information security controls",
  },
];

export default function ReportsPage() {
  const [kind, setKind] = useState("technical");

  const scans = useQuery({
    queryKey: ["scans-completed"],
    queryFn: async () => {
      const all = await api<Scan[]>("/api/v1/scans");
      return all.filter((s) => s.status === "completed" || s.status === "failed");
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

  const reportUrl = (scanId: string, fmt: "html" | "pdf") => {
    const t = tokenStore.get();
    return `${API_BASE}/api/v1/scans/${scanId}/report?kind=${kind}&fmt=${fmt}${
      t ? `&_t=${encodeURIComponent(t)}` : ""
    }`;
  };

  return (
    <div>
      <PageHeader
        title="Reports"
        description="Export scan results in compliance-friendly formats."
      />

      {/* Template selector */}
      <div className="mb-4 grid gap-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {TEMPLATES.map((t) => (
          <button
            key={t.kind}
            onClick={() => setKind(t.kind)}
            className={`rounded-lg border p-3 text-left transition ${
              kind === t.kind
                ? "border-accent/50 bg-accent/10 ring-2 ring-accent/30"
                : "border-border-subtle bg-bg-elevated hover:border-border"
            }`}
          >
            <div className="flex items-center gap-2">
              <FileBarChart2
                className={`h-4 w-4 ${
                  kind === t.kind ? "text-accent" : "text-slate-500"
                }`}
              />
              <span className="text-sm font-semibold">{t.label}</span>
            </div>
            <p className="mt-1 text-[11px] text-slate-400">{t.desc}</p>
          </button>
        ))}
      </div>

      {scans.isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      )}
      {scans.error && (
        <p className="text-severity-critical">
          {scans.error instanceof ApiError ? scans.error.message : "Error"}
        </p>
      )}

      <div className="card overflow-hidden p-0">
        <table className="table">
          <thead>
            <tr>
              <th>Target</th>
              <th>Status</th>
              <th>Finished</th>
              <th>Findings</th>
              <th className="text-right">Export</th>
            </tr>
          </thead>
          <tbody>
            {!scans.isLoading &&
              scans.data?.map((s) => {
                const target = targetMap.get(s.target_id);
                const total = Object.values(s.summary || {}).reduce(
                  (a, b) => a + Number(b ?? 0),
                  0,
                );
                return (
                  <tr key={s.id}>
                    <td>
                      {target ? (
                        <div className="min-w-0">
                          <div className="truncate text-slate-100">
                            {target.name}
                          </div>
                          <div className="truncate font-mono text-[11px] text-slate-500">
                            {target.base_url}
                          </div>
                        </div>
                      ) : (
                        <span className="font-mono text-xs text-slate-500">
                          {s.id.slice(0, 8)}…
                        </span>
                      )}
                    </td>
                    <td>
                      <StatusPill status={s.status} />
                    </td>
                    <td className="text-xs text-slate-400">
                      {s.finished_at
                        ? new Date(s.finished_at).toLocaleString()
                        : "—"}
                    </td>
                    <td className="text-xs">
                      {total > 0 ? (
                        <span className="font-mono text-slate-200">{total}</span>
                      ) : (
                        <span className="text-slate-500">—</span>
                      )}
                    </td>
                    <td className="text-right">
                      <div className="inline-flex items-center gap-1">
                        <a
                          className="btn-ghost px-2 py-1 text-xs"
                          href={reportUrl(s.id, "html")}
                          target="_blank"
                          rel="noopener"
                        >
                          <FileText className="h-3.5 w-3.5" />
                          HTML
                        </a>
                        <a
                          className="btn-ghost px-2 py-1 text-xs"
                          href={reportUrl(s.id, "pdf")}
                        >
                          <Download className="h-3.5 w-3.5" />
                          PDF
                        </a>
                      </div>
                    </td>
                  </tr>
                );
              })}
            {!scans.isLoading && scans.data?.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState
                    icon={FileBarChart2}
                    title="No completed scans"
                    description="Run a scan first — once it completes, it will be exportable here."
                  />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

    </div>
  );
}
