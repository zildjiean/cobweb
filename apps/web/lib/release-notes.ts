export const CURRENT_VERSION = "0.1.0";

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
