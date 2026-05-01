"use client";

import { useQuery } from "@tanstack/react-query";
import { Target as TargetIcon } from "lucide-react";
import { api } from "@/lib/api";

interface Target {
  id: string;
  name: string;
  base_url: string;
  status: string;
}

interface Project {
  id: string;
  name: string;
}

interface Props {
  value: string;
  onChange: (id: string) => void;
  projectId?: string;
  onProjectChange?: (id: string) => void;
  className?: string;
}

/**
 * Target/project picker — `target_id` is selected via the right select,
 * but optionally narrowed by project on the left.
 */
export function TargetFilter({
  value,
  onChange,
  projectId,
  onProjectChange,
  className = "",
}: Props) {
  const targets = useQuery({
    queryKey: ["targets-all"],
    queryFn: () => api<Target[]>("/api/v1/targets"),
  });

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/api/v1/projects"),
    enabled: onProjectChange !== undefined,
  });

  // If a project is selected, narrow the target list to that project's targets
  const projectTargetIds = new Set<string>();
  if (projectId && targets.data) {
    targets.data
      .filter((t) => (t as Target & { project_id?: string }).project_id === projectId)
      .forEach((t) => projectTargetIds.add(t.id));
  }
  const visibleTargets = projectId
    ? (targets.data ?? []).filter((t) =>
        // Cast to access the project_id field that the API actually returns
        (t as Target & { project_id?: string }).project_id === projectId,
      )
    : targets.data ?? [];

  return (
    <div className={`flex flex-wrap items-end gap-2 ${className}`}>
      {onProjectChange && (
        <label className="min-w-[160px]">
          <span className="label">Project</span>
          <select
            className="input"
            value={projectId ?? ""}
            onChange={(e) => onProjectChange(e.target.value)}
          >
            <option value="">All projects</option>
            {projects.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="flex-1 min-w-[240px]">
        <span className="label flex items-center gap-1">
          <TargetIcon className="h-3 w-3" />
          Target / website
        </span>
        <select
          className="input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={targets.isLoading}
        >
          <option value="">All targets</option>
          {visibleTargets.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} · {t.base_url}
            </option>
          ))}
          {visibleTargets.length === 0 && !targets.isLoading && (
            <option disabled>
              {projectId ? "No targets in this project" : "No targets yet"}
            </option>
          )}
        </select>
      </label>
    </div>
  );
}
