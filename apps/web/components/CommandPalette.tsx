"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bug,
  FileText,
  FolderKanban,
  History,
  LayoutDashboard,
  Plug,
  ScanLine,
  Search,
  Settings,
  Shield,
  Sparkles,
  Target,
} from "lucide-react";
import { api } from "@/lib/api";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  group: "Navigate" | "Projects" | "Targets" | "Scans";
  icon: React.ComponentType<{ className?: string }>;
  href: string;
}

interface ProjectMin {
  id: string;
  name: string;
  slug: string;
}
interface TargetMin {
  id: string;
  name: string;
  base_url: string;
}
interface ScanMin {
  id: string;
  engine: string;
  status: string;
  created_at: string;
}

const NAV_ITEMS: CommandItem[] = [
  { id: "nav-dashboard", group: "Navigate", label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { id: "nav-scans", group: "Navigate", label: "Scans", href: "/scans", icon: ScanLine },
  { id: "nav-vulns", group: "Navigate", label: "Vulnerabilities", href: "/vulnerabilities", icon: Bug },
  { id: "nav-reports", group: "Navigate", label: "Reports", href: "/reports", icon: FileText },
  { id: "nav-projects", group: "Navigate", label: "Projects", href: "/projects", icon: FolderKanban },
  { id: "nav-targets", group: "Navigate", label: "Targets", href: "/targets", icon: Target },
  { id: "nav-integrations", group: "Navigate", label: "Integrations", href: "/integrations", icon: Plug },
  { id: "nav-audit", group: "Navigate", label: "Audit log", href: "/audit", icon: History },
  { id: "nav-admin", group: "Navigate", label: "Admin", href: "/admin", icon: Shield, hint: "Account · Org" },
  { id: "nav-llm", group: "Navigate", label: "LLM translation settings", href: "/admin/llm", icon: Sparkles, hint: "Provider · Model · Prompt" },
];

export default function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Mac uses Cmd, others Ctrl
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIdx(0);
      // focus on next tick
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const projects = useQuery({
    queryKey: ["palette-projects"],
    queryFn: () => api<ProjectMin[]>("/api/v1/projects"),
    enabled: open,
    staleTime: 60_000,
  });
  const targets = useQuery({
    queryKey: ["palette-targets"],
    queryFn: () => api<TargetMin[]>("/api/v1/targets"),
    enabled: open,
    staleTime: 60_000,
  });
  const scans = useQuery({
    queryKey: ["palette-scans"],
    queryFn: () => api<ScanMin[]>("/api/v1/scans"),
    enabled: open,
    staleTime: 30_000,
  });

  const items: CommandItem[] = useMemo(() => {
    const all: CommandItem[] = [...NAV_ITEMS];
    for (const p of projects.data ?? []) {
      all.push({
        id: `proj-${p.id}`,
        group: "Projects",
        label: p.name,
        hint: p.slug,
        href: `/projects`,
        icon: FolderKanban,
      });
    }
    for (const t of targets.data ?? []) {
      all.push({
        id: `tgt-${t.id}`,
        group: "Targets",
        label: t.name,
        hint: t.base_url,
        href: `/targets`,
        icon: Target,
      });
    }
    for (const s of (scans.data ?? []).slice(0, 50)) {
      all.push({
        id: `scan-${s.id}`,
        group: "Scans",
        label: `${s.engine} · ${s.id.slice(0, 8)}`,
        hint: `${s.status} · ${new Date(s.created_at).toLocaleString()}`,
        href: `/scans/${s.id}`,
        icon: ScanLine,
      });
    }
    return all;
  }, [projects.data, targets.data, scans.data]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) =>
      `${it.label} ${it.hint ?? ""} ${it.group}`.toLowerCase().includes(q),
    );
  }, [items, query]);

  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  const grouped = useMemo(() => {
    const map = new Map<CommandItem["group"], CommandItem[]>();
    for (const it of filtered) {
      const arr = map.get(it.group);
      if (arr) arr.push(it);
      else map.set(it.group, [it]);
    }
    return Array.from(map.entries());
  }, [filtered]);

  const onPick = (it: CommandItem) => {
    setOpen(false);
    router.push(it.href);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-start justify-center bg-black/60 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-bg-elevated shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border-subtle px-3 py-2.5">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search nav, projects, targets, recent scans…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-slate-500"
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIdx((i) => Math.max(0, i - 1));
              } else if (e.key === "Enter" && filtered[activeIdx]) {
                e.preventDefault();
                onPick(filtered[activeIdx]);
              }
            }}
          />
          <kbd className="hidden font-mono text-[10px] text-slate-500 sm:inline">
            esc
          </kbd>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-2">
          {filtered.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-slate-500">
              No matches
            </p>
          )}
          {grouped.map(([group, list]) => (
            <div key={group} className="mb-2">
              <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500">
                {group}
              </div>
              {list.map((it) => {
                const idx = filtered.indexOf(it);
                const active = idx === activeIdx;
                const Icon = it.icon;
                return (
                  <button
                    key={it.id}
                    type="button"
                    onMouseEnter={() => setActiveIdx(idx)}
                    onClick={() => onPick(it)}
                    className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition ${
                      active
                        ? "bg-accent/12 text-accent"
                        : "text-slate-200 hover:bg-bg/60"
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0 opacity-70" />
                    <span className="min-w-0 flex-1 truncate">{it.label}</span>
                    {it.hint && (
                      <span className="hidden truncate font-mono text-[11px] text-slate-500 sm:inline">
                        {it.hint}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-border-subtle px-3 py-1.5 text-[10px] text-slate-500">
          <div className="flex items-center gap-3">
            <span><kbd className="font-mono">↑↓</kbd> navigate</span>
            <span><kbd className="font-mono">↵</kbd> open</span>
          </div>
          <span><kbd className="font-mono">⌘K</kbd> / <kbd className="font-mono">Ctrl+K</kbd></span>
        </div>
      </div>
    </div>
  );
}
