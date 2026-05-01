"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FolderKanban, Plus } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/EmptyState";

interface Project {
  id: string;
  name: string;
  slug: string;
  description: string;
  created_at: string;
}

export default function ProjectsPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/api/v1/projects"),
  });

  const create = useMutation({
    mutationFn: (body: { name: string; slug: string; description: string }) =>
      api<Project>("/api/v1/projects", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.push({ kind: "success", title: `Created project ${p.name}` });
      setOpen(false);
      setName("");
      setSlug("");
      setDescription("");
    },
    onError: (err) =>
      toast.push({
        kind: "error",
        title: "Failed to create project",
        description: err instanceof ApiError ? err.message : undefined,
      }),
  });

  return (
    <div>
      <PageHeader
        title="Projects"
        description="Top-level grouping for related targets and scans."
        action={
          <button className="btn-primary" onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" />
            New project
          </button>
        }
      />

      {open && (
        <div className="card mb-4 animate-fade-in">
          <h3 className="mb-3 text-sm font-semibold">New project</h3>
          <form
            className="grid gap-3 md:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate({ name, slug, description });
            }}
          >
            <label>
              <span className="label">Name</span>
              <input
                className="input"
                placeholder="Marketing site"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label>
              <span className="label">Slug</span>
              <input
                className="input"
                placeholder="marketing-site"
                pattern="[a-z0-9][a-z0-9-]*"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                required
              />
            </label>
            <label>
              <span className="label">Description (optional)</span>
              <input
                className="input"
                placeholder="What this project covers"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <div className="md:col-span-3 flex justify-end gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => setOpen(false)}
              >
                Cancel
              </button>
              <button className="btn-primary" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create"}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}
      {error && (
        <p className="text-sm text-severity-critical">
          {error instanceof ApiError ? error.message : "Error"}
        </p>
      )}
      {!isLoading && data?.length === 0 && (
        <div className="card">
          <EmptyState
            icon={FolderKanban}
            title="No projects yet"
            description="Create a project to start adding targets and running scans."
            action={
              <button
                className="btn-primary text-sm"
                onClick={() => setOpen(true)}
              >
                <Plus className="h-3.5 w-3.5" />
                New project
              </button>
            }
          />
        </div>
      )}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {data?.map((p) => (
          <div key={p.id} className="card card-hover">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-accent/15 text-accent">
                <FolderKanban className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-base font-semibold">{p.name}</div>
                <div className="font-mono text-[11px] text-slate-500">
                  {p.slug}
                </div>
              </div>
            </div>
            <p className="mt-3 text-sm text-slate-300">
              {p.description || (
                <span className="italic text-slate-500">No description</span>
              )}
            </p>
            <p className="mt-3 text-[11px] text-slate-500">
              Created {new Date(p.created_at).toLocaleDateString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
