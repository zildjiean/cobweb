"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader, Skeleton } from "@/components/ui/EmptyState";

interface LLMSettings {
  provider: "gemini" | "openrouter" | null;
  model: string | null;
  has_api_key: boolean;
  prompt_template: string;
  updated_at: string | null;
}

export default function LLMSettingsPage() {
  const qc = useQueryClient();
  const settings = useQuery({
    queryKey: ["llm-settings"],
    queryFn: () => api<LLMSettings>("/api/v1/org/llm-settings"),
  });

  const [provider, setProvider] = useState<"gemini" | "openrouter">("gemini");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [prompt, setPrompt] = useState("");
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    setProvider(settings.data.provider ?? "gemini");
    setModel(settings.data.model ?? defaultModel(settings.data.provider ?? "gemini"));
    setPrompt(settings.data.prompt_template);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: (body: {
      provider: string;
      model: string;
      api_key?: string;
      prompt_template: string;
    }) =>
      api<LLMSettings>("/api/v1/org/llm-settings", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["llm-settings"] });
      setApiKey("");
    },
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const body: {
      provider: string;
      model: string;
      api_key?: string;
      prompt_template: string;
    } = {
      provider,
      model: model.trim(),
      prompt_template: prompt,
    };
    if (apiKey.trim()) body.api_key = apiKey.trim();
    save.mutate(body);
  };

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="LLM translation"
        description="Configure the model used to translate findings into Thai. Used today for issue translation; report translation will use the same settings later."
      />

      {settings.isLoading && <Skeleton className="h-64" />}

      {settings.data && (
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="card space-y-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-accent" />
              <h2 className="section-title">Provider</h2>
            </div>

            <label className="block">
              <span className="label">Provider</span>
              <select
                className="input"
                value={provider}
                onChange={(e) => {
                  const p = e.target.value as "gemini" | "openrouter";
                  setProvider(p);
                  if (!model) setModel(defaultModel(p));
                }}
              >
                <option value="gemini">Google Gemini</option>
                <option value="openrouter">OpenRouter</option>
              </select>
            </label>

            <label className="block">
              <span className="label">Model</span>
              <input
                className="input font-mono"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={defaultModel(provider)}
                required
              />
              <p className="mt-1 text-[11px] text-slate-500">
                {provider === "gemini"
                  ? "e.g. gemini-2.0-flash, gemini-2.5-pro"
                  : "e.g. anthropic/claude-3.7-sonnet, openai/gpt-4o-mini, google/gemini-2.5-flash"}
              </p>
            </label>

            <label className="block">
              <span className="label">
                API key{" "}
                {settings.data.has_api_key && (
                  <span className="ml-1 text-[11px] text-emerald-300">
                    (saved — leave blank to keep)
                  </span>
                )}
              </span>
              <div className="flex gap-2">
                <input
                  type={showKey ? "text" : "password"}
                  className="input flex-1 font-mono"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={
                    settings.data.has_api_key
                      ? "•••••••••••••••• (saved)"
                      : "paste your provider API key"
                  }
                  autoComplete="off"
                />
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setShowKey((v) => !v)}
                >
                  {showKey ? "Hide" : "Show"}
                </button>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">
                Stored encrypted in the database (Fernet, key derived from the
                server secret). Never returned by the API after saving.
              </p>
            </label>
          </div>

          <div className="card space-y-2">
            <h2 className="section-title">Default prompt</h2>
            <p className="text-[12px] text-slate-400">
              System prompt sent with every translation. Members can override
              per-call from the issue dialog.
            </p>
            <textarea
              className="input min-h-[160px] font-mono text-xs leading-relaxed"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              required
            />
          </div>

          {save.error && (
            <p className="text-severity-critical text-sm">
              {save.error instanceof ApiError
                ? save.error.message
                : "Save failed"}
            </p>
          )}

          <div className="flex items-center justify-between">
            <p className="text-[11px] text-slate-500">
              {settings.data.updated_at
                ? `Last updated ${new Date(settings.data.updated_at).toLocaleString()}`
                : "Not configured yet"}
            </p>
            <button
              type="submit"
              className="btn-primary"
              disabled={save.isPending}
            >
              {save.isPending ? "Saving…" : "Save settings"}
            </button>
          </div>
        </form>
      )}

      {settings.error instanceof ApiError && settings.error.status === 403 && (
        <p className="card text-sm text-amber-300">
          Only org admins can configure LLM settings.
        </p>
      )}
    </div>
  );
}

function defaultModel(p: "gemini" | "openrouter"): string {
  return p === "gemini" ? "gemini-2.0-flash" : "google/gemini-2.5-flash";
}
