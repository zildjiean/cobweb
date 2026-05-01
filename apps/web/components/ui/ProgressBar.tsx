"use client";

interface ProgressBarProps {
  progress: number;
  status: string;
  size?: "sm" | "md";
  className?: string;
}

export function ProgressBar({
  progress,
  status,
  size = "md",
  className = "",
}: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, progress));
  const fillClass =
    status === "failed"
      ? "progress-fill progress-fill-failed"
      : status === "completed"
      ? "progress-fill progress-fill-done"
      : "progress-fill progress-fill-active";
  const height = size === "sm" ? "h-1.5" : "h-2";
  return (
    <div className={`progress-track ${height} ${className}`}>
      <div
        className={fillClass}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

const PROFILE_ESTIMATE_SEC: Record<string, number> = {
  quick: 180,
  high: 600,
  full: 1800,
  custom: 300,
};

export function formatEta(
  startedAt: string | null,
  progress: number,
  profile: string,
  status: string,
): string | null {
  if (status === "completed" || status === "failed" || status === "cancelled") {
    return null;
  }
  if (!startedAt) return null;
  const elapsed = (Date.now() - new Date(startedAt).getTime()) / 1000;
  if (elapsed < 4) return "starting…";
  // Two estimates blended:
  // (a) extrapolate from current progress vs elapsed
  // (b) profile-based rough estimate
  // Use whichever is *larger* (more conservative) to avoid promising 0s when
  // progress is stuck early.
  const profileEst = PROFILE_ESTIMATE_SEC[profile] ?? 300;
  const profileRemain = Math.max(0, profileEst - elapsed);
  let progressRemain = profileRemain;
  if (progress > 8) {
    const totalEst = (elapsed / progress) * 100;
    progressRemain = Math.max(0, totalEst - elapsed);
  }
  const remain = Math.max(profileRemain, progressRemain);
  if (remain < 30) return "wrapping up…";
  if (remain < 60) return `~${Math.round(remain)}s remaining`;
  const m = Math.floor(remain / 60);
  const s = Math.round(remain % 60);
  if (m < 60) return `~${m}m ${s}s remaining`;
  const h = Math.floor(m / 60);
  return `~${h}h ${m % 60}m remaining`;
}
