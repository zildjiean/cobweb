"use client";

import { useEffect, useRef, useState } from "react";
import { Megaphone, Sparkles, X } from "lucide-react";
import { CURRENT_VERSION, RELEASES } from "@/lib/release-notes";

const STORAGE_KEY = "cobweb.lastSeenReleaseVersion";

export default function ReleaseNotesBell() {
  const [open, setOpen] = useState(false);
  const [hasUnseen, setHasUnseen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Initial check — runs once on mount, in the browser only.
  useEffect(() => {
    const seen = window.localStorage.getItem(STORAGE_KEY);
    setHasUnseen(seen !== CURRENT_VERSION);
  }, []);

  // Click-outside + Esc to close
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const handleToggle = () => {
    setOpen((prev) => {
      const next = !prev;
      if (next && hasUnseen) {
        window.localStorage.setItem(STORAGE_KEY, CURRENT_VERSION);
        setHasUnseen(false);
      }
      return next;
    });
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={handleToggle}
        className={`relative rounded-md p-2 transition ${
          open
            ? "bg-bg-elevated text-white"
            : "text-slate-400 hover:bg-bg-elevated hover:text-white"
        }`}
        aria-label="Release notes"
        title="Release notes"
      >
        <Megaphone className="h-4 w-4" />
        {hasUnseen && (
          <span className="absolute right-1 top-1 flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-severity-critical opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-severity-critical ring-2 ring-bg" />
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Release notes"
          className="absolute right-0 top-full z-50 mt-2 w-[380px] origin-top-right animate-fade-in overflow-hidden rounded-xl border border-border bg-bg-elevated shadow-card-hover"
        >
          <div className="flex items-center justify-between border-b border-border-subtle bg-gradient-to-r from-accent/10 to-transparent px-4 py-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent" />
              <h3 className="text-sm font-semibold">What's new</h3>
              <span className="badge border border-accent/30 bg-accent/10 text-accent">
                v{CURRENT_VERSION}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-1 text-slate-400 hover:bg-bg hover:text-white"
              aria-label="Close"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="max-h-[70vh] overflow-y-auto">
            {RELEASES.map((rel) => (
              <article
                key={rel.version}
                className="border-b border-border-subtle/60 p-4 last:border-0"
              >
                <header className="mb-2 flex items-baseline justify-between gap-2">
                  <h4 className="text-sm font-semibold text-slate-100">
                    {rel.title}
                  </h4>
                  <span className="font-mono text-[11px] text-slate-500">
                    {rel.date}
                  </span>
                </header>
                <ul className="space-y-2.5 text-xs">
                  {rel.highlights.map((h, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
                      <div className="min-w-0">
                        <p className="font-medium text-slate-200">{h.label}</p>
                        {h.detail && (
                          <p className="mt-0.5 text-slate-400">{h.detail}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
