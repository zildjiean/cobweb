"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, Info, ShieldAlert, X } from "lucide-react";

type Tone = "danger" | "warning" | "info";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: Tone;
  loading?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

const TONE_STYLES: Record<
  Tone,
  { icon: typeof AlertTriangle; iconClass: string; ringClass: string; btnClass: string }
> = {
  danger: {
    icon: ShieldAlert,
    iconClass: "text-severity-critical",
    ringClass: "bg-severity-critical/15 ring-1 ring-severity-critical/30",
    btnClass: "bg-severity-critical text-white hover:bg-severity-critical/90",
  },
  warning: {
    icon: AlertTriangle,
    iconClass: "text-severity-medium",
    ringClass: "bg-severity-medium/15 ring-1 ring-severity-medium/30",
    btnClass: "bg-severity-medium text-bg hover:bg-severity-medium/90",
  },
  info: {
    icon: Info,
    iconClass: "text-accent",
    ringClass: "bg-accent/15 ring-1 ring-accent/30",
    btnClass: "bg-accent text-white hover:bg-accent-hover",
  },
};

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
  loading = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  // Esc to close + autofocus the cancel button (safer default than confirm)
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) onClose();
      // Tab focus trap between Cancel and Confirm
      if (e.key === "Tab") {
        const active = document.activeElement;
        if (active === confirmRef.current && !e.shiftKey) {
          e.preventDefault();
          cancelRef.current?.focus();
        } else if (active === cancelRef.current && e.shiftKey) {
          e.preventDefault();
          confirmRef.current?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    cancelRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, loading, onClose]);

  // Lock body scroll while modal is open
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  const styles = TONE_STYLES[tone];
  const Icon = styles.icon;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
    >
      <div
        className="absolute inset-0 animate-fade-in bg-black/60 backdrop-blur-sm"
        onClick={() => !loading && onClose()}
      />
      <div className="relative w-full max-w-md origin-center animate-fade-in overflow-hidden rounded-xl border border-border bg-bg-elevated shadow-card-hover">
        <button
          type="button"
          onClick={() => !loading && onClose()}
          disabled={loading}
          className="absolute right-3 top-3 rounded p-1 text-slate-400 transition hover:bg-bg hover:text-white disabled:opacity-50"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="flex items-start gap-3 px-5 pb-2 pt-5">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${styles.ringClass}`}
          >
            <Icon className={`h-5 w-5 ${styles.iconClass}`} />
          </div>
          <div className="min-w-0 flex-1 pt-1">
            <h3
              id="confirm-dialog-title"
              className="pr-6 text-base font-semibold text-slate-100"
            >
              {title}
            </h3>
            {description && (
              <div className="mt-1.5 text-sm text-slate-400">{description}</div>
            )}
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border-subtle bg-bg/40 px-4 py-3">
          <button
            ref={cancelRef}
            type="button"
            className="btn-ghost text-sm"
            onClick={onClose}
            disabled={loading}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={`btn text-sm ${styles.btnClass}`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
