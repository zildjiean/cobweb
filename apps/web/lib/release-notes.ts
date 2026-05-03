export const CURRENT_VERSION = "0.4.0";

export type Highlight = {
  label: string;
  detail?: string;
};

export type Release = {
  version: string;
  date: string;
  title: string;
  highlights: Highlight[];
};

export const RELEASES: Release[] = [
  {
    version: "0.4.0",
    date: "2026-05-03",
    title: "AI fixes, replay, schedules, and authenticated scans",
    highlights: [
      {
        label: "AI remediation per finding",
        detail:
          "Click 'Ask AI for fix' in any finding — Cobweb sends the metadata, request, and response to your configured LLM and returns a focused remediation plan (What broke / Fix / Verify) in markdown.",
      },
      {
        label: "Scheduled scans",
        detail:
          "New /schedules page lets you run a target on a recurring cadence — hourly, daily, weekly, or monthly. Each fires automatically (background loop in the API) and supports on-demand 'run now', pause/resume, and delete.",
      },
      {
        label: "Authenticated scanning",
        detail:
          "Targets now accept HTTP header (e.g. Authorization: Bearer …) or Cookie credentials, encrypted at rest with Fernet. Both Nuclei and ZAP send them on every request — covering JWT-protected APIs and session-based apps.",
      },
      {
        label: "HTTP request/response replay + copy-as-curl",
        detail:
          "Findings now carry the raw HTTP that triggered them. The Request section has a 'curl' badge that copies a working curl command straight to clipboard for verification.",
      },
      {
        label: "Scan diff view",
        detail:
          "Scan detail page now shows a 4-card diff vs the previous scan: New / Regression / Fixed / Recurring — answer 'are we making progress' at a glance.",
      },
      {
        label: "make ship + web-restart",
        detail:
          "New Makefile targets: 'make web-restart' rebuilds + restarts the production web server, 'make ship' adds a git push. No more dev-mode lag in production browsing.",
      },
    ],
  },
  {
    version: "0.3.0",
    date: "2026-05-03",
    title: "Reports, AI, and a polished UI",
    highlights: [
      {
        label: "Professional report system",
        detail:
          "Five report kinds (executive, technical, OWASP Top 10, PCI-DSS 6.5, ISO 27001) — each with risk-grade card (A–F), severity donut, page numbers, and properly grouped findings. PDF export via WeasyPrint.",
      },
      {
        label: "LLM integration",
        detail:
          "Per-org AI credentials (encrypted at rest) for OpenAI / OpenRouter / Anthropic. Powers finding translation and the new bulk compliance-mapping job (`make bulk-map`) that classifies template_ids into OWASP / PCI / ISO categories.",
      },
      {
        label: "High scan profile",
        detail:
          "New profile between Quick and Full — runs CVE templates filtered to medium-or-higher severity. Solid middle ground when Quick misses too much and Full is overkill.",
      },
      {
        label: "Observability stack",
        detail:
          "Prometheus + Grafana + cAdvisor + node-exporter shipped in docker-compose. Pre-built dashboards for API latency, scan throughput, container resources, and ZAP/worker health.",
      },
      {
        label: "Command palette",
        detail:
          "Cmd/Ctrl+K opens a quick navigator across every page, target, scan, and admin action. No more menu hunting.",
      },
      {
        label: "Design system + UI polish",
        detail:
          "Unified design tokens, refreshed admin pages, finding detail modal with markdown rendering, refined scan detail view, and many small polish passes across the dashboard.",
      },
      {
        label: "ZAP tuning for bigger boxes",
        detail:
          "Memory limits and JVM heap retuned for hosts with more RAM — High and Full profiles now run reliably without OOM.",
      },
    ],
  },
  {
    version: "0.1.0",
    date: "2026-05-01",
    title: "First scan, first findings",
    highlights: [
      {
        label: "Live findings stream",
        detail:
          "Findings now appear on the scan detail page as Nuclei discovers them — no more waiting for the whole scan to finish.",
      },
      {
        label: "Smoother progress bar",
        detail:
          "Progress interpolates over time per profile estimate, with a moving sheen + ETA badge while a scan runs.",
      },
      {
        label: "Per-website filter",
        detail:
          "Dashboard and Vulnerabilities pages can now narrow to a single project + target.",
      },
      {
        label: "Target lifecycle",
        detail:
          "Delete targets (cascades to their scans/findings/vulns). Dev mode auto-verifies new targets to keep iteration fast.",
      },
      {
        label: "Nuclei profiles dialed in",
        detail:
          "Quick = tag-based (tech / misconfig / exposure / takeover, ~1–3 min). High = CVE templates ≥ medium severity. Full = no filter.",
      },
      {
        label: "UI/UX overhaul",
        detail:
          "New design system, grouped sidebar, breadcrumbs, toasts, empty-states, and live event stream on every scan.",
      },
    ],
  },
];
