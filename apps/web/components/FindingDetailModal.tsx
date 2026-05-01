"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Check, Copy, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { SeverityPill } from "@/components/ui/Badges";
import { Skeleton } from "@/components/ui/EmptyState";

export interface FindingDetail {
  id: string;
  scan_id: string;
  target_id: string;
  template_id: string;
  name: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  matched_at: string;
  description: string | null;
  remediation: string | null;
  cve: string | null;
  cwe: string | null;
  cvss: string | null;
  matcher_name: string | null;
  request: string | null;
  response: string | null;
  raw: Record<string, unknown>;
  dedupe_hash: string;
  created_at: string;
}

interface Props {
  scanId: string;
  findingId: string | null;
  onClose: () => void;
}

export default function FindingDetailModal({
  scanId,
  findingId,
  onClose,
}: Props) {
  const open = findingId !== null;

  const detail = useQuery({
    queryKey: ["finding-detail", scanId, findingId],
    queryFn: () =>
      api<FindingDetail>(`/api/v1/scans/${scanId}/findings/${findingId}`),
    enabled: open && !!findingId,
  });

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-border bg-bg-elevated shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border-subtle bg-bg-elevated/95 px-5 py-4 backdrop-blur">
          {detail.data ? (
            <div className="min-w-0">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <SeverityPill severity={detail.data.severity} />
                <span className="font-mono text-xs text-slate-400">
                  {detail.data.template_id}
                </span>
                {detail.data.cve && (
                  <span className="badge bg-bg/60 font-mono text-slate-300">
                    {detail.data.cve}
                  </span>
                )}
              </div>
              <h2 className="break-words text-lg font-semibold text-slate-100">
                {detail.data.name}
              </h2>
              <p className="mt-1 break-all font-mono text-xs text-slate-500">
                {detail.data.matched_at}
              </p>
            </div>
          ) : (
            <Skeleton className="h-12 w-2/3" />
          )}
          <button
            onClick={onClose}
            className="rounded p-1.5 text-slate-400 transition hover:bg-bg/60 hover:text-white"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {detail.isLoading && (
          <div className="space-y-3 p-5">
            <Skeleton className="h-20" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        )}
        {detail.error && (
          <p className="p-5 text-severity-critical">
            {detail.error instanceof ApiError
              ? detail.error.message
              : "Error loading finding"}
          </p>
        )}

        {detail.data && (
          <div className="space-y-4 p-5">
            <Section label="Metadata">
              <dl className="grid grid-cols-1 gap-y-1 text-sm md:grid-cols-[140px_1fr]">
                <Row label="CVE" value={detail.data.cve} mono />
                <Row label="CWE" value={detail.data.cwe} mono />
                <Row label="CVSS" value={detail.data.cvss} mono />
                <Row label="Matcher" value={detail.data.matcher_name} mono />
                <Row label="Dedupe hash" value={detail.data.dedupe_hash} mono />
                <Row
                  label="First seen"
                  value={new Date(detail.data.created_at).toLocaleString()}
                />
              </dl>
            </Section>

            {detail.data.description && (
              <Section label="Description">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                  {detail.data.description}
                </p>
              </Section>
            )}

            {detail.data.remediation && (
              <Section label="Remediation">
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                  {detail.data.remediation}
                </p>
              </Section>
            )}

            {detail.data.request && (
              <Section label="Request payload sent by scanner">
                <CopyBlock text={detail.data.request} />
              </Section>
            )}

            {detail.data.response && (
              <Section label="Response from target">
                <CopyBlock text={detail.data.response} />
              </Section>
            )}

            <Section label="Raw scanner output">
              <CopyBlock text={JSON.stringify(detail.data.raw, null, 2)} />
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="section-title mb-2">{label}</h3>
      {children}
    </section>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
}) {
  return (
    <>
      <dt className="text-slate-400">{label}</dt>
      <dd
        className={`${
          mono ? "font-mono text-xs" : ""
        } break-all text-slate-200`}
      >
        {value || "—"}
      </dd>
    </>
  );
}

function CopyBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="relative">
      <pre className="max-h-72 overflow-auto rounded-md bg-bg/80 p-3 pr-10 font-mono text-xs leading-relaxed text-slate-200">
        {text}
      </pre>
      <button
        onClick={copy}
        className="absolute right-1.5 top-1.5 rounded p-1.5 text-slate-400 transition hover:bg-bg-elevated hover:text-white"
        aria-label="Copy"
        title="Copy"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-emerald-400" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </button>
    </div>
  );
}
