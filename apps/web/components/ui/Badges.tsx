"use client";

import { AlertTriangle, CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";

export type Severity = "critical" | "high" | "medium" | "low" | "info";

const SEV_DOT: Record<Severity, string> = {
  critical: "bg-severity-critical",
  high: "bg-severity-high",
  medium: "bg-severity-medium",
  low: "bg-severity-low",
  info: "bg-severity-info",
};

export function SeverityPill({
  severity,
  size = "sm",
}: {
  severity: Severity;
  size?: "xs" | "sm";
}) {
  const px = size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`pill ${px} text-severity-${severity} bg-severity-${severity}/15`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${SEV_DOT[severity]}`} />
      {severity}
    </span>
  );
}

const STATUS_TONE: Record<string, { cls: string; Icon?: React.ComponentType<{ className?: string }> }> = {
  queued: { cls: "bg-slate-700/60 text-slate-300", Icon: Clock },
  running: { cls: "bg-accent/15 text-accent", Icon: Loader2 },
  completed: { cls: "bg-emerald-500/15 text-emerald-300", Icon: CheckCircle2 },
  failed: { cls: "bg-severity-critical/15 text-severity-critical", Icon: XCircle },
  cancelled: { cls: "bg-slate-600/40 text-slate-300", Icon: XCircle },
  pending_verification: { cls: "bg-amber-500/15 text-amber-300", Icon: AlertTriangle },
  verified: { cls: "bg-emerald-500/15 text-emerald-300", Icon: CheckCircle2 },
  disabled: { cls: "bg-slate-700/60 text-slate-400" },
};

export function StatusPill({ status }: { status: string }) {
  const t = STATUS_TONE[status] ?? { cls: "bg-slate-700/40 text-slate-300" };
  const Icon = t.Icon;
  return (
    <span className={`pill ${t.cls}`}>
      {Icon && <Icon className={`h-3 w-3 ${status === "running" ? "animate-spin" : ""}`} />}
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function EngineBadge({ engine }: { engine: string }) {
  const tone =
    engine === "zap"
      ? "bg-purple-500/15 text-purple-300 border-purple-500/30"
      : "bg-cyan-500/15 text-cyan-300 border-cyan-500/30";
  return (
    <span className={`badge border ${tone}`}>
      {engine === "zap" ? "ZAP" : "Nuclei"}
    </span>
  );
}
