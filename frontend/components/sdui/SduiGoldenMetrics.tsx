"use client";

type MetricItem = {
  id?: string;
  label?: string;
  value?: number | string;
  color?: string;
};

type Props = {
  metrics?: MetricItem[];
};

function metricTone(color?: string): { bar: string; text: string; track: string } {
  const tone = (color || "").trim().toLowerCase();
  if (tone === "warning") {
    return { bar: "var(--warning)", text: "var(--warning)", track: "color-mix(in oklab, var(--warning) 12%, var(--surface-2))" };
  }
  if (tone === "error" || tone === "danger") {
    return { bar: "var(--danger)", text: "var(--danger)", track: "color-mix(in oklab, var(--danger) 12%, var(--surface-2))" };
  }
  if (tone === "accent") {
    return { bar: "var(--accent)", text: "var(--accent)", track: "color-mix(in oklab, var(--accent) 12%, var(--surface-2))" };
  }
  return { bar: "var(--success)", text: "var(--success)", track: "color-mix(in oklab, var(--success) 12%, var(--surface-2))" };
}

function coerceValue(value: number | string | undefined): number {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.min(100, value));
  if (typeof value === "string") {
    const n = Number.parseFloat(value.replace(/[^\d.-]/g, ""));
    if (Number.isFinite(n)) return Math.max(0, Math.min(100, n));
  }
  return 0;
}

export function SduiGoldenMetrics({ metrics = [] }: Props) {
  if (!metrics.length) {
    return (
      <div className="flex min-h-[140px] w-full items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-6 text-xs text-[var(--text-muted)]">
        暂无黄金指标
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {metrics.map((metric, index) => {
        const label = String(metric.label || `指标 ${index + 1}`).trim();
        const value = coerceValue(metric.value);
        const tone = metricTone(metric.color);
        return (
          <div
            key={metric.id || `${label}-${index}`}
            className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-4"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="text-xs font-medium text-[var(--text-secondary)]">{label}</span>
              <span className="text-xl font-semibold tabular-nums" style={{ color: tone.text }}>
                {Math.round(value)}%
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full" style={{ background: tone.track }}>
              <div
                className="h-full rounded-full transition-[width] duration-300"
                style={{ width: `${value}%`, background: tone.bar }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
