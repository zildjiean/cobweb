"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard,
  FolderKanban,
  ScanLine,
  Bug,
  CalendarClock,
  Target,
  FileText,
  Plug,
  History,
  Shield,
  LogOut,
  ChevronRight,
  Menu,
  X,
} from "lucide-react";
import { api, tokenStore } from "@/lib/api";
import CommandPalette from "@/components/CommandPalette";
import ReleaseNotesBell from "@/components/ReleaseNotesBell";
import ThemeToggle from "@/components/ThemeToggle";
import { CURRENT_VERSION } from "@/lib/release-notes";

const NAV_GROUPS: {
  label: string;
  items: { href: string; label: string; icon: typeof LayoutDashboard }[];
}[] = [
  {
    label: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    ],
  },
  {
    label: "Security",
    items: [
      { href: "/scans", label: "Scans", icon: ScanLine },
      { href: "/schedules", label: "Schedules", icon: CalendarClock },
      { href: "/vulnerabilities", label: "Vulnerabilities", icon: Bug },
      { href: "/reports", label: "Reports", icon: FileText },
    ],
  },
  {
    label: "Configuration",
    items: [
      { href: "/projects", label: "Projects", icon: FolderKanban },
      { href: "/targets", label: "Targets", icon: Target },
      { href: "/integrations", label: "Integrations", icon: Plug },
    ],
  },
  {
    label: "Admin",
    items: [
      { href: "/audit", label: "Audit", icon: History },
      { href: "/admin", label: "Admin", icon: Shield },
    ],
  },
];

interface Me {
  email: string;
  full_name: string;
  role: string | null;
  org_id: string | null;
  org_name: string | null;
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!tokenStore.get()) {
      router.replace("/login");
      return;
    }
    api<Me>("/api/v1/auth/me")
      .then(setMe)
      .catch(() => {
        tokenStore.clear();
        router.replace("/login");
      });
  }, [router]);

  const breadcrumb = useMemo(() => {
    if (!pathname) return null;
    const parts = pathname.split("/").filter(Boolean);
    if (parts.length === 0) return null;
    const top = parts[0];
    const label = top.charAt(0).toUpperCase() + top.slice(1);
    return { top: label, sub: parts[1] };
  }, [pathname]);

  return (
    <div className="flex min-h-screen">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col border-r border-border-subtle bg-bg-elevated/95 backdrop-blur transition-transform md:static md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between px-5 py-5">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-accent to-accent-subtle text-xs font-bold text-white shadow-glow">
              C
            </div>
            <div className="leading-tight">
              <div className="text-lg font-semibold tracking-tight">
                Cob<span className="text-accent">web</span>
              </div>
              <div className="font-mono text-[10px] text-slate-500">
                v{CURRENT_VERSION}
              </div>
            </div>
          </div>
          <button
            className="text-slate-400 hover:text-white md:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Close menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto px-2 pb-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <p className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500">
                {group.label}
              </p>
              <div className="space-y-0.5">
                {group.items.map(({ href, label, icon: Icon }) => {
                  const active = pathname?.startsWith(href);
                  return (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => setMobileOpen(false)}
                      className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition ${
                        active
                          ? "bg-accent/12 text-accent shadow-[inset_2px_0_0_0] shadow-accent"
                          : "text-slate-300 hover:bg-bg/60 hover:text-white"
                      }`}
                    >
                      <Icon className={`h-4 w-4 ${active ? "" : "text-slate-500"}`} />
                      {label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>

        <div className="border-t border-border-subtle p-3">
          <div className="flex items-center gap-2.5 rounded-md bg-bg/40 p-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent/15 text-xs font-semibold text-accent">
              {(me?.full_name || me?.email || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-slate-200">
                {me?.full_name || me?.email || "…"}
              </p>
              <p className="truncate text-[11px] text-slate-500">
                {me?.role ?? "—"}
              </p>
            </div>
            <button
              onClick={() => {
                tokenStore.clear();
                router.replace("/login");
              }}
              className="rounded p-1.5 text-slate-400 transition hover:bg-bg-elevated hover:text-severity-critical"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex flex-1 flex-col min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-4 border-b border-border-subtle bg-bg/80 px-4 backdrop-blur md:px-6">
          <div className="flex items-center gap-3">
            <button
              className="rounded p-1.5 text-slate-400 hover:bg-bg-elevated hover:text-white md:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open menu"
            >
              <Menu className="h-5 w-5" />
            </button>
            <nav className="flex items-center gap-1.5 text-sm">
              <span className="text-slate-500">{me?.org_name || "—"}</span>
              {breadcrumb && (
                <>
                  <ChevronRight className="h-3.5 w-3.5 text-slate-600" />
                  <span className="font-medium text-slate-200">
                    {breadcrumb.top}
                  </span>
                  {breadcrumb.sub && (
                    <>
                      <ChevronRight className="h-3.5 w-3.5 text-slate-600" />
                      <span className="font-mono text-xs text-slate-400">
                        {breadcrumb.sub.length > 12
                          ? `${breadcrumb.sub.slice(0, 8)}…`
                          : breadcrumb.sub}
                      </span>
                    </>
                  )}
                </>
              )}
            </nav>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <button
              type="button"
              onClick={() => {
                const ev = new KeyboardEvent("keydown", {
                  key: "k",
                  metaKey: true,
                  bubbles: true,
                });
                window.dispatchEvent(ev);
              }}
              className="hidden items-center gap-1.5 rounded-md border border-border-subtle bg-bg/40 px-2 py-1 hover:border-border hover:text-slate-200 sm:inline-flex"
              title="Open command palette (⌘K / Ctrl+K)"
            >
              <span>Search</span>
              <kbd className="rounded bg-bg-elevated px-1 font-mono text-[10px] text-slate-500">
                ⌘K
              </kbd>
            </button>
            <ThemeToggle />
            <ReleaseNotesBell />
            <span className="hidden sm:inline">{me?.email}</span>
            {me?.role && (
              <span className="badge border border-accent/30 bg-accent/10 text-accent">
                {me.role}
              </span>
            )}
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
