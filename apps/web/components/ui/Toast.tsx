"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

type ToastKind = "info" | "success" | "error" | "warning";

interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  description?: string;
}

interface ToastContextValue {
  push: (t: Omit<Toast, "id">) => void;
}

const ToastCtx = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((cur) => [...cur, { ...t, id }]);
    setTimeout(() => {
      setToasts((cur) => cur.filter((x) => x.id !== id));
    }, 4500);
  }, []);

  return (
    <ToastCtx.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onClose={() =>
            setToasts((cur) => cur.filter((x) => x.id !== t.id))
          } />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setClosing(true), 4000);
    return () => clearTimeout(t);
  }, []);

  const tone: Record<ToastKind, string> = {
    info: "border-accent/40 bg-accent/10 text-slate-100",
    success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-50",
    error: "border-severity-critical/50 bg-severity-critical/10 text-rose-50",
    warning: "border-amber-500/40 bg-amber-500/10 text-amber-50",
  };
  const dot: Record<ToastKind, string> = {
    info: "bg-accent",
    success: "bg-emerald-400",
    error: "bg-severity-critical",
    warning: "bg-amber-400",
  };

  return (
    <div
      className={`pointer-events-auto rounded-lg border p-3 shadow-card-hover backdrop-blur transition ${
        closing ? "opacity-0 translate-x-2" : "animate-slide-in-right"
      } ${tone[toast.kind]}`}
    >
      <div className="flex items-start gap-2.5">
        <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot[toast.kind]}`} />
        <div className="flex-1">
          <p className="text-sm font-medium">{toast.title}</p>
          {toast.description && (
            <p className="mt-0.5 text-xs text-slate-300">{toast.description}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 transition hover:text-white"
          aria-label="dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}
