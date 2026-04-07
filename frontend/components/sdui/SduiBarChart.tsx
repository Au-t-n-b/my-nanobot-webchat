"use client";

import { useMemo } from "react";

import type { SduiBarDatum } from "@/lib/sdui";

const DEFAULT_BAR_COLORS = [
  "color-mix(in oklab, var(--accent) 70%, var(--surface-2))",
  "var(--success)",
  "var(--warning)",
  "color-mix(in oklab, var(--danger) 65%, var(--surface-2))",
  "color-mix(in oklab, var(--text-muted) 50%, var(--surface-2))",
];

type Props = {
  data: SduiBarDatum[];
  valueUnit?: string;
};

export function SduiBarChart({ data, valueUnit }: Props) {
  const { rows, max } = useMemo(() => {
    const safe = data.filter((d) => Number.isFinite(d.value));
    const m = Math.max(1, ...safe.map((d) => d.value));
    return { rows: safe, max: m };
  }, [data]);

  if (rows.length === 0) {
    return (
      <div className="flex min-h-[140px] w-full items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-6 text-xs text-[var(--text-muted)]">
        暂无分类数据
      </div>
    );
  }

  const unit = valueUnit ?? "";

  return (
    <div className="flex w-full min-w-0 flex-col gap-3">
      <div className="flex h-40 min-h-[9rem] w-full items-end justify-between gap-1.5 px-0.5 sm:gap-2">
        {rows.map((d, i) => {
          const hPct = Math.max(6, (d.value / max) * 100);
          const bg = d.color ?? DEFAULT_BAR_COLORS[i % DEFAULT_BAR_COLORS.length];
          return (
            <div key={`${d.label}-${i}`} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1.5">
              <div className="flex w-full flex-1 flex-col items-center justify-end">
                <div
                  className="w-full max-w-[3rem] rounded-t-md transition-[height] duration-300 ease-out"
                  style={{
                    height: `${hPct}%`,
                    minHeight: "6px",
                    background: bg,
                    boxShadow: "inset 0 1px 0 color-mix(in oklab, var(--surface-1) 25%, transparent)",
                  }}
                  title={`${d.label}: ${d.value}${unit}`}
                />
              </div>
              <span className="line-clamp-2 w-full text-center text-[10px] leading-tight text-[var(--text-muted)] sm:text-[11px]">
                {d.label}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-[var(--border-subtle)] pt-2 text-[11px] text-[var(--text-secondary)]">
        {rows.map((d, i) => (
          <span key={`sum-${d.label}-${i}`} className="tabular-nums">
            <span className="text-[var(--text-muted)]">{d.label}</span>{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {d.value}
              {unit}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
