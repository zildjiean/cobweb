"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import {
  CalendarClock,
  Loader2,
  Pause,
  Play,
  Plus,
  Power,
  Trash2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import ConfirmDialog from "@/components/ui/ConfirmDialog";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";
import { useToast } from "@/components/ui/Toast";

type Frequency = "hourly" | "daily" | "weekly" | "monthly";
type Profile = "quick" | "high" | "full" | "custom";

interface Schedule {
  id: string;
  org_id: string;
  project_id: string;
  target_id: string;
  name: string;
  profile: Profile;
  engine: string;
  frequency: Frequency;
  hour_of_day: number;
  day_of_week: number;
  day_of_month: number;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_scan_id: string | null;
  created_at: string;
  updated_at: string;
}

interface Target {
  id: string;
  base_url: string;
  status: string;
  project_id: string;
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

export default function SchedulesPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Schedule | null>(null);

  const schedules = useQuery({
    queryKey: ["schedules"],
    queryFn: () => api<Schedule[]>("/api/v1/schedules"),
  });

  const targets = useQuery({
    queryKey: ["targets"],
    queryFn: () => api<Target[]>("/api/v1/targets"),
  });

  const toggleEnabled = useMutation({
    mutationFn: (s: Schedule) =>
      api<Schedule>(`/api/v1/schedules/${s.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !s.enabled }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });

  const runNow = useMutation({
    mutationFn: (s: Schedule) =>
      api<Schedule>(`/api/v1/schedules/${s.id}/run`, { method: "POST" }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["schedules"] });
      qc.invalidateQueries({ queryKey: ["scans"] });
      toast.push({
        kind: "success",
        title: "Scan triggered",
        description: `Schedule "${data.name}" started a scan now.`,
      });
    },
    onError: (err) => {
      toast.push({
        kind: "error",
        title: "Trigger failed",
        description:
          err instanceof ApiError ? err.message.slice(0, 160) : undefined,
      });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/api/v1/schedules/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedules"] });
      setConfirmDelete(null);
      toast.push({ kind: "success", title: "Schedule deleted" });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scheduled scans"
        description="Run scans on a recurring cadence — hourly, daily, weekly, or monthly. Each fires automatically and can also be triggered on demand."
        action={
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="btn-primary inline-flex items-center gap-1.5"
          >
            <Plus className="h-4 w-4" />
            New schedule
          </button>
        }
      />

      {schedules.isLoading && <Skeleton className="h-32" />}
      {schedules.data && schedules.data.length === 0 && !showCreate && (
        <EmptyState
          icon={CalendarClock}
          title="No schedules yet"
          description="Create one to keep an eye on a target without remembering to scan it manually."
          action={
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="btn-primary inline-flex items-center gap-1.5"
            >
              <Plus className="h-4 w-4" />
              New schedule
            </button>
          }
        />
      )}

      {showCreate && (
        <ScheduleForm
          targets={targets.data ?? []}
          onCancel={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            qc.invalidateQueries({ queryKey: ["schedules"] });
          }}
        />
      )}

      {schedules.data && schedules.data.length > 0 && (
        <div className="card overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-bg/40 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Name</th>
                <th className="px-4 py-2 text-left font-medium">Target</th>
                <th className="px-4 py-2 text-left font-medium">Cadence</th>
                <th className="px-4 py-2 text-left font-medium">Profile</th>
                <th className="px-4 py-2 text-left font-medium">Next run</th>
                <th className="px-4 py-2 text-left font-medium">Last run</th>
                <th className="px-4 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {schedules.data.map((s) => {
                const target = targets.data?.find((t) => t.id === s.target_id);
                return (
                  <tr key={s.id} className="hover:bg-bg/40">
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-100">{s.name}</div>
                      <div className="text-[11px] uppercase tracking-wide text-slate-500">
                        {s.engine}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {target ? (
                        <span className="break-all font-mono text-xs">
                          {target.base_url}
                        </span>
                      ) : (
                        <span className="text-slate-500">missing</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-300">
                      {describeFrequency(s)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="badge bg-bg/60 font-mono text-xs uppercase text-slate-300">
                        {s.profile}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-300">
                      {s.enabled
                        ? formatRelative(s.next_run_at)
                        : <span className="text-slate-500">disabled</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-300">
                      {s.last_scan_id ? (
                        <Link
                          href={`/scans/${s.last_scan_id}`}
                          className="text-accent hover:underline"
                        >
                          {formatRelative(s.last_run_at)}
                        </Link>
                      ) : (
                        <span className="text-slate-500">never</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => runNow.mutate(s)}
                          disabled={runNow.isPending}
                          className="btn-ghost px-2"
                          title="Run now"
                        >
                          {runNow.isPending && runNow.variables?.id === s.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Play className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => toggleEnabled.mutate(s)}
                          disabled={toggleEnabled.isPending}
                          className="btn-ghost px-2"
                          title={s.enabled ? "Disable" : "Enable"}
                        >
                          {s.enabled ? (
                            <Pause className="h-3.5 w-3.5" />
                          ) : (
                            <Power className="h-3.5 w-3.5 text-emerald-400" />
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDelete(s)}
                          className="btn-ghost px-2 text-severity-critical"
                          title="Delete"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete !== null}
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => confirmDelete && remove.mutate(confirmDelete.id)}
        title="Delete schedule?"
        description={`"${confirmDelete?.name ?? ""}" will stop running. Past scans aren't affected.`}
        confirmLabel="Delete"
        tone="danger"
      />
    </div>
  );
}

function ScheduleForm({
  targets,
  onCreated,
  onCancel,
}: {
  targets: Target[];
  onCreated: () => void;
  onCancel: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [targetId, setTargetId] = useState(targets[0]?.id ?? "");
  const [profile, setProfile] = useState<Profile>("quick");
  const [frequency, setFrequency] = useState<Frequency>("daily");
  const [hourOfDay, setHourOfDay] = useState(9);
  const [dayOfWeek, setDayOfWeek] = useState(0);
  const [dayOfMonth, setDayOfMonth] = useState(1);

  const create = useMutation({
    mutationFn: () =>
      api<Schedule>("/api/v1/schedules", {
        method: "POST",
        body: JSON.stringify({
          target_id: targetId,
          name: name.trim(),
          profile,
          engine: "nuclei",
          frequency,
          hour_of_day: hourOfDay,
          day_of_week: dayOfWeek,
          day_of_month: dayOfMonth,
          enabled: true,
        }),
      }),
    onSuccess: () => {
      toast.push({ kind: "success", title: "Schedule created" });
      onCreated();
    },
    onError: (err) => {
      toast.push({
        kind: "error",
        title: "Could not create schedule",
        description:
          err instanceof ApiError ? err.message.slice(0, 200) : undefined,
      });
    },
  });

  const verifiedTargets = targets.filter((t) => t.status === "verified");

  return (
    <form
      className="card space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (!name.trim() || !targetId) return;
        create.mutate();
      }}
    >
      <h2 className="section-title">New schedule</h2>

      <div className="grid gap-4 md:grid-cols-2">
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-wide text-slate-400">
            Name
          </span>
          <input
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Nightly quick scan of staging"
            required
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-wide text-slate-400">
            Target
          </span>
          <select
            className="input"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            required
          >
            {verifiedTargets.length === 0 && (
              <option value="" disabled>
                No verified targets — verify one first
              </option>
            )}
            {verifiedTargets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.base_url}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-wide text-slate-400">
            Profile
          </span>
          <select
            className="input"
            value={profile}
            onChange={(e) => setProfile(e.target.value as Profile)}
          >
            <option value="quick">Quick — tag-based, ~1-3 min</option>
            <option value="high">High — CVE templates ≥ medium</option>
            <option value="full">Full — every template</option>
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-xs uppercase tracking-wide text-slate-400">
            Frequency
          </span>
          <select
            className="input"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value as Frequency)}
          >
            <option value="hourly">Hourly (top of every hour)</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </label>

        {frequency !== "hourly" && (
          <label className="space-y-1">
            <span className="text-xs uppercase tracking-wide text-slate-400">
              Hour of day (UTC)
            </span>
            <select
              className="input"
              value={hourOfDay}
              onChange={(e) => setHourOfDay(Number(e.target.value))}
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
          </label>
        )}
        {frequency === "weekly" && (
          <label className="space-y-1">
            <span className="text-xs uppercase tracking-wide text-slate-400">
              Day of week
            </span>
            <select
              className="input"
              value={dayOfWeek}
              onChange={(e) => setDayOfWeek(Number(e.target.value))}
            >
              {WEEKDAYS.map((d, i) => (
                <option key={i} value={i}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        )}
        {frequency === "monthly" && (
          <label className="space-y-1">
            <span className="text-xs uppercase tracking-wide text-slate-400">
              Day of month (1-28)
            </span>
            <input
              type="number"
              min={1}
              max={28}
              className="input"
              value={dayOfMonth}
              onChange={(e) => setDayOfMonth(Number(e.target.value))}
            />
          </label>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 border-t border-border-subtle pt-3">
        <button type="button" className="btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn-primary inline-flex items-center gap-1.5"
          disabled={create.isPending || !name.trim() || !targetId}
        >
          {create.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Create schedule
        </button>
      </div>
    </form>
  );
}

function describeFrequency(s: Schedule): string {
  const time = `${String(s.hour_of_day).padStart(2, "0")}:00 UTC`;
  switch (s.frequency) {
    case "hourly":
      return "Every hour (top of hour)";
    case "daily":
      return `Every day at ${time}`;
    case "weekly":
      return `Every ${WEEKDAYS[s.day_of_week] ?? "?"} at ${time}`;
    case "monthly":
      return `Day ${s.day_of_month} of each month at ${time}`;
  }
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const diffMs = d.getTime() - Date.now();
  const absMin = Math.abs(diffMs) / 60_000;
  if (absMin < 1) return "now";
  const future = diffMs > 0;
  const fmt = (val: number, unit: string) =>
    future ? `in ${val}${unit}` : `${val}${unit} ago`;
  if (absMin < 60) return fmt(Math.round(absMin), "m");
  const absHr = absMin / 60;
  if (absHr < 24) return fmt(Math.round(absHr), "h");
  const absDay = absHr / 24;
  if (absDay < 14) return fmt(Math.round(absDay), "d");
  return d.toLocaleDateString();
}
