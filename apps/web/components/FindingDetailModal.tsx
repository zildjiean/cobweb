"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Check, Copy, Languages, RefreshCw, Sparkles, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { SeverityPill } from "@/components/ui/Badges";
import { Skeleton } from "@/components/ui/EmptyState";
import Markdown from "@/components/ui/Markdown";
import { useToast } from "@/components/ui/Toast";

interface TranslationResult {
  finding_id: string;
  lang: string;
  provider: string;
  model: string;
  content: string;
  cached: boolean;
  tokens_in: number | null;
  tokens_out: number | null;
  created_at: string;
}

interface RemediationResult {
  finding_id: string;
  provider: string;
  model: string;
  content: string;
  cached: boolean;
  tokens_in: number | null;
  tokens_out: number | null;
  created_at: string;
}

export interface FindingAttackDetails {
  method: string | null;
  parameter: string | null;
  payload: string | null;
  evidence: string | null;
  input_vector: string | null;
  confidence: string | null;
  extra: Record<string, unknown>;
}

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
  attack_details: FindingAttackDetails | null;
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

  const [translation, setTranslation] = useState<TranslationResult | null>(null);
  const [showCustomPrompt, setShowCustomPrompt] = useState(false);
  const [customPrompt, setCustomPrompt] = useState("");
  const [remediation, setRemediation] = useState<RemediationResult | null>(null);
  const toast = useToast();

  useEffect(() => {
    setTranslation(null);
    setShowCustomPrompt(false);
    setCustomPrompt("");
    setRemediation(null);
  }, [findingId]);

  const translate = useMutation({
    mutationFn: (opts: { refresh: boolean }) =>
      api<TranslationResult>(`/api/v1/findings/${findingId}/translate`, {
        method: "POST",
        body: JSON.stringify({
          lang: "th",
          refresh: opts.refresh,
          custom_prompt: customPrompt.trim() || undefined,
        }),
      }),
    onSuccess: (data) => {
      setTranslation(data);
      toast.push({
        kind: "success",
        title: data.cached ? "Loaded cached translation" : "Translated to Thai",
        description: `${data.provider} · ${data.model}${
          data.tokens_in != null
            ? ` · ${data.tokens_in}/${data.tokens_out ?? "?"} tokens`
            : ""
        }`,
      });
    },
    onError: (err) => {
      const status = err instanceof ApiError ? err.status : 0;
      toast.push({
        kind: "error",
        title:
          status === 412
            ? "LLM not configured"
            : status === 429
              ? "Provider rate limit"
              : "Translation failed",
        description:
          status === 412
            ? "Set provider, model, and API key in Admin → LLM translation."
            : err instanceof Error
              ? err.message.slice(0, 160)
              : undefined,
      });
    },
  });

  const remediate = useMutation({
    mutationFn: (opts: { refresh: boolean }) =>
      api<RemediationResult>(`/api/v1/findings/${findingId}/remediation`, {
        method: "POST",
        body: JSON.stringify({ refresh: opts.refresh }),
      }),
    onSuccess: (data) => {
      setRemediation(data);
      toast.push({
        kind: "success",
        title: data.cached ? "Loaded cached remediation" : "AI remediation ready",
        description: `${data.provider} · ${data.model}${
          data.tokens_in != null
            ? ` · ${data.tokens_in}/${data.tokens_out ?? "?"} tokens`
            : ""
        }`,
      });
    },
    onError: (err) => {
      const status = err instanceof ApiError ? err.status : 0;
      toast.push({
        kind: "error",
        title:
          status === 412
            ? "LLM not configured"
            : status === 429
              ? "Provider rate limit"
              : "AI remediation failed",
        description:
          status === 412
            ? "Set provider, model, and API key in Admin → LLM."
            : err instanceof Error
              ? err.message.slice(0, 160)
              : undefined,
      });
    },
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

            <Section label="Translate to Thai">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => translate.mutate({ refresh: false })}
                    disabled={translate.isPending}
                    className="btn-primary inline-flex items-center gap-1.5"
                  >
                    <Languages className="h-3.5 w-3.5" />
                    {translate.isPending
                      ? "Translating…"
                      : translation
                        ? "Translation shown"
                        : "Translate"}
                  </button>
                  {translation && (
                    <button
                      type="button"
                      onClick={() => translate.mutate({ refresh: true })}
                      disabled={translate.isPending}
                      className="btn-ghost inline-flex items-center gap-1.5 text-xs"
                      title="Force re-translate (skip cache)"
                    >
                      <RefreshCw className="h-3 w-3" />
                      Refresh
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setShowCustomPrompt((v) => !v)}
                    className="btn-ghost text-xs"
                  >
                    {showCustomPrompt ? "Hide custom prompt" : "Custom prompt"}
                  </button>
                </div>
                {showCustomPrompt && (
                  <textarea
                    className="input min-h-[80px] font-mono text-xs"
                    placeholder="Override the org default prompt for this translation only…"
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                  />
                )}
                {translate.error instanceof ApiError && (
                  <p className="text-sm text-severity-critical">
                    {translate.error.status === 412
                      ? "LLM not configured — ask an org admin to set provider, model, and API key in Admin → LLM translation."
                      : translate.error.message}
                  </p>
                )}
                {translation && (
                  <div className="rounded-md border border-border-subtle bg-bg/60 p-3">
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                      <span className="font-mono">
                        {translation.provider} · {translation.model}
                      </span>
                      {translation.cached && (
                        <span className="badge bg-emerald-500/15 text-emerald-300">
                          cached
                        </span>
                      )}
                      {(translation.tokens_in != null ||
                        translation.tokens_out != null) && (
                        <span className="font-mono">
                          tokens in/out: {translation.tokens_in ?? "—"}/
                          {translation.tokens_out ?? "—"}
                        </span>
                      )}
                    </div>
                    <Markdown>{translation.content}</Markdown>
                  </div>
                )}
              </div>
            </Section>

            <Section label="AI remediation">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => remediate.mutate({ refresh: false })}
                    disabled={remediate.isPending}
                    className="btn-primary inline-flex items-center gap-1.5"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {remediate.isPending
                      ? "Asking AI…"
                      : remediation
                        ? "Remediation shown"
                        : "Ask AI for fix"}
                  </button>
                  {remediation && (
                    <button
                      type="button"
                      onClick={() => remediate.mutate({ refresh: true })}
                      disabled={remediate.isPending}
                      className="btn-ghost inline-flex items-center gap-1.5 text-xs"
                      title="Force re-ask (skip cache)"
                    >
                      <RefreshCw className="h-3 w-3" />
                      Refresh
                    </button>
                  )}
                  <p className="text-xs text-slate-500">
                    Uses your org&apos;s configured LLM. Includes finding
                    metadata + truncated request/response as context.
                  </p>
                </div>
                {remediate.error instanceof ApiError && (
                  <p className="text-sm text-severity-critical">
                    {remediate.error.status === 412
                      ? "LLM not configured — ask an org admin to set provider, model, and API key in Admin → LLM."
                      : remediate.error.message}
                  </p>
                )}
                {remediation && (
                  <div className="rounded-md border border-accent/30 bg-accent/5 p-3">
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                      <span className="font-mono">
                        {remediation.provider} · {remediation.model}
                      </span>
                      {remediation.cached && (
                        <span className="badge bg-emerald-500/15 text-emerald-300">
                          cached
                        </span>
                      )}
                      {(remediation.tokens_in != null ||
                        remediation.tokens_out != null) && (
                        <span className="font-mono">
                          tokens in/out: {remediation.tokens_in ?? "—"}/
                          {remediation.tokens_out ?? "—"}
                        </span>
                      )}
                    </div>
                    <Markdown>{remediation.content}</Markdown>
                  </div>
                )}
              </div>
            </Section>

            {detail.data.attack_details && hasAnyAttackField(detail.data.attack_details) && (
              <Section label="Attack details">
                <dl className="grid grid-cols-1 gap-y-1 text-sm md:grid-cols-[140px_1fr]">
                  <Row label="Method" value={detail.data.attack_details.method} mono />
                  <Row label="Parameter" value={detail.data.attack_details.parameter} mono />
                  <Row label="Input vector" value={detail.data.attack_details.input_vector} mono />
                  <Row label="Confidence" value={detail.data.attack_details.confidence} />
                  {detail.data.attack_details.payload && (
                    <>
                      <dt className="text-slate-400">Payload</dt>
                      <dd className="break-all">
                        <CopyBlock text={detail.data.attack_details.payload} />
                      </dd>
                    </>
                  )}
                  {detail.data.attack_details.evidence && (
                    <>
                      <dt className="text-slate-400">Evidence</dt>
                      <dd className="break-all">
                        <CopyBlock text={detail.data.attack_details.evidence} />
                      </dd>
                    </>
                  )}
                </dl>
              </Section>
            )}

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
                <CopyBlock
                  text={detail.data.request}
                  curl={httpRequestToCurl(
                    detail.data.request,
                    detail.data.matched_at,
                  )}
                />
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

function hasAnyAttackField(d: FindingAttackDetails): boolean {
  return Boolean(
    d.method ||
      d.parameter ||
      d.payload ||
      d.evidence ||
      d.input_vector ||
      d.confidence,
  );
}

function CopyBlock({ text, curl }: { text: string; curl?: string }) {
  const [copied, setCopied] = useState<"text" | "curl" | null>(null);
  const copy = (kind: "text" | "curl", payload: string) => {
    navigator.clipboard?.writeText(payload);
    setCopied(kind);
    setTimeout(() => setCopied(null), 1500);
  };
  return (
    <div className="relative">
      <pre className="max-h-72 overflow-auto rounded-md bg-bg/80 p-3 pr-10 font-mono text-xs leading-relaxed text-slate-200">
        {text}
      </pre>
      <div className="absolute right-1.5 top-1.5 flex items-center gap-1">
        {curl && (
          <button
            onClick={() => copy("curl", curl)}
            className="rounded px-1.5 py-1 text-[10px] font-mono uppercase text-slate-400 transition hover:bg-bg-elevated hover:text-white"
            title="Copy as curl command"
          >
            {copied === "curl" ? "copied" : "curl"}
          </button>
        )}
        <button
          onClick={() => copy("text", text)}
          className="rounded p-1.5 text-slate-400 transition hover:bg-bg-elevated hover:text-white"
          aria-label="Copy"
          title="Copy raw"
        >
          {copied === "text" ? (
            <Check className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
      </div>
    </div>
  );
}

/** Parse a raw HTTP request and emit a curl command.
 *
 * Best-effort: malformed requests fall back to a plain `curl <url>` using the
 * matched URL hint. Headers like Host / Content-Length are skipped because
 * curl emits them itself.
 */
function httpRequestToCurl(raw: string, urlHint: string | null): string {
  const text = raw.replace(/\r\n/g, "\n").trimStart();
  const headerEnd = text.indexOf("\n\n");
  const headerSection = headerEnd === -1 ? text : text.slice(0, headerEnd);
  const body = headerEnd === -1 ? "" : text.slice(headerEnd + 2);
  const lines = headerSection.split("\n").filter((l) => l.length > 0);
  if (lines.length === 0) {
    return urlHint ? `curl ${shellQuote(urlHint)}` : "curl";
  }
  const requestLine = lines[0]!.split(/\s+/);
  const method = requestLine[0] || "GET";
  const path = requestLine[1] || "/";
  const headerMap = new Map<string, string>();
  const skip = new Set(["host", "content-length"]);
  for (const line of lines.slice(1)) {
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    const val = line.slice(idx + 1).trim();
    if (skip.has(key.toLowerCase())) continue;
    headerMap.set(key, val);
  }
  const hostHeader = lines
    .slice(1)
    .find((l) => l.toLowerCase().startsWith("host:"))
    ?.slice(5)
    .trim();
  let url: string;
  if (path.startsWith("http://") || path.startsWith("https://")) {
    url = path;
  } else if (hostHeader) {
    const scheme = guessScheme(urlHint, hostHeader);
    url = `${scheme}://${hostHeader}${path}`;
  } else if (urlHint) {
    try {
      const u = new URL(urlHint);
      url = `${u.protocol}//${u.host}${path}`;
    } catch {
      url = path;
    }
  } else {
    url = path;
  }
  const parts: string[] = [`curl ${shellQuote(url)}`];
  if (method !== "GET") parts.push(`  -X ${method}`);
  for (const [k, v] of headerMap) {
    parts.push(`  -H ${shellQuote(`${k}: ${v}`)}`);
  }
  if (body.trim().length > 0) {
    parts.push(`  --data-raw ${shellQuote(body)}`);
  }
  return parts.join(" \\\n");
}

function shellQuote(s: string): string {
  return `'${s.replace(/'/g, "'\\''")}'`;
}

function guessScheme(urlHint: string | null, host: string): string {
  if (urlHint?.startsWith("https://")) return "https";
  if (urlHint?.startsWith("http://")) return "http";
  if (host.endsWith(":443")) return "https";
  if (host.endsWith(":80")) return "http";
  return "https"; // default to https — modern web is mostly TLS
}
