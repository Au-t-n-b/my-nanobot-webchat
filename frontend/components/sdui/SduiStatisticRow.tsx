"use client";

import type { SduiStatisticRowItem } from "@/lib/sdui";
import { semanticTextClass } from "@/components/sdui/sduiSemanticColor";

type Props = {
  items: SduiStatisticRowItem[];
};

/** 横向一排指标卡（等价于 Row + 多个 Statistic，供大盘 JSON 使用 `type: StatisticRow`） */
export function SduiStatisticRow({ items }: Props) {
  if (!items?.length) {
    return (
      <div className="rounded-lg border border-dashed border-[var(--border-subtle)] px-3 py-4 text-center text-xs ui-text-muted">
        暂无指标项
      </div>
    );
  }
  return (
    <div className="metrics-grid w-full">
      {items.map((it, i) => {
        const v = it.value === null || it.value === undefined ? "" : it.value;
        const c = semanticTextClass(it.color);
        return (
          <div
            key={`${it.title}:${i}`}
            className="min-w-0 rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-3 text-center shadow-sm"
          >
            <div className="mb-1 text-[11px] font-medium text-[var(--text-muted)]">{it.title}</div>
            <div className={`text-2xl font-bold tabular-nums tracking-tight text-[var(--text-primary)] ${c}`.trim()}>
              {v}
            </div>
          </div>
        );
      })}
    </div>
  );
}
