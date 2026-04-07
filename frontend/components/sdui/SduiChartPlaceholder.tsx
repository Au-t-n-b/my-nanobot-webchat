"use client";

import { BarChart3, PieChart } from "lucide-react";

import type { SduiChartVariant } from "@/lib/sdui";

type Props = {
  variant: SduiChartVariant;
  caption?: string;
};

export function SduiChartPlaceholder({ variant, caption }: Props) {
  const Icon = variant === "pie" ? PieChart : BarChart3;
  const label = variant === "pie" ? "满足度分布" : "分类统计";

  return (
    <div
      className="flex min-h-[168px] w-full min-w-0 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-8 dark:bg-[var(--surface-3)]/60"
      role="img"
      aria-label={label}
    >
      <Icon className="h-10 w-10 text-[var(--text-muted)] opacity-80" strokeWidth={1.25} aria-hidden />
      <p className="text-center text-xs text-[var(--text-muted)]">{caption ?? `${label}（数据就绪后展示）`}</p>
    </div>
  );
}
