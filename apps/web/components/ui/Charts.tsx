"use client";

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  fill?: boolean;
}

export function Sparkline({
  values,
  width = 120,
  height = 36,
  className = "stroke-accent",
  fill = true,
}: SparklineProps) {
  if (values.length === 0) {
    return (
      <svg width={width} height={height} className="text-slate-700">
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="currentColor"
          strokeDasharray="3 3"
        />
      </svg>
    );
  }
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = Math.max(max - min, 1);
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const pts = values.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return [x, y] as const;
  });
  const d = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`).join(" ");
  const fillPath = fill
    ? `${d} L${width},${height} L0,${height} Z`
    : null;
  return (
    <svg width={width} height={height} className={className} viewBox={`0 0 ${width} ${height}`}>
      {fillPath && <path d={fillPath} fill="currentColor" opacity="0.15" />}
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

interface BarChartProps {
  data: { label: string; value: number; color?: string }[];
  height?: number;
}

export function HBarChart({ data, height = 8 }: BarChartProps) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="space-y-3">
      {data.map((d) => {
        const pct = (d.value / max) * 100;
        return (
          <div key={d.label}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium uppercase tracking-wide text-slate-300">
                {d.label}
              </span>
              <span className="font-mono text-slate-200">{d.value}</span>
            </div>
            <div
              className="overflow-hidden rounded bg-bg/60"
              style={{ height }}
            >
              <div
                className={`h-full transition-all ${d.color ?? "bg-accent"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
