"use client";

import type { SduiGanttBar, SduiGanttLaneRow, SduiSemanticColor } from "@/lib/sdui";

type Props = {
  title?: string;
  caption?: string;
  lanes?: SduiGanttLaneRow[];
};

const BAR_COLOR: Record<SduiSemanticColor, string> = {
  success: "bg-[color-mix(in_oklab,var(--success)_78%,var(--surface-3))]",
  warning: "bg-[color-mix(in_oklab,var(--warning)_78%,var(--surface-3))]",
  error: "bg-[color-mix(in_oklab,var(--danger)_72%,var(--surface-3))]",
  accent: "bg-[color-mix(in_oklab,var(--accent)_72%,var(--surface-3))]",
  subtle: "bg-[var(--surface-3)]",
};

function barClass(color?: string): string {
  if (!color) return BAR_COLOR.accent;
  if (color in BAR_COLOR) return BAR_COLOR[color as SduiSemanticColor];
  return BAR_COLOR.accent;
}

/** 简易甘特轨（封闭世界：无自由像素，仅用语义色条） */
export function SduiGanttLane({ title, caption, lanes }: Props) {
  const rows = lanes?.length ? lanes : [{ label: "示例轨道", bars: [{ label: "块", widthPct: 40, startPct: 10, color: "accent" }] }];

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--canvas-rail)] p-3 sm:p-4 space-y-3">
      {title ? <div className="text-xs font-semibold ui-text-primary">{title}</div> : null}
      {caption ? <div className="text-[11px] ui-text-secondary leading-relaxed">{caption}</div> : null}
      <div className="space-y-2.5">
        {rows.map((lane, li) => (
          <div key={`${lane.label}-${li}`} className="min-w-0 space-y-1">
            <div className="text-[10px] font-medium ui-text-muted truncate">{lane.label}</div>
            <div className="h-6 w-full rounded-md bg-[var(--surface-3)] border border-[var(--border-subtle)] overflow-hidden flex relative">
              {(lane.bars ?? ([] as SduiGanttBar[])).map((b, bi) => {
                const start = Math.max(0, Math.min(100, b.startPct ?? 0));
                const w = Math.max(0, Math.min(100 - start, b.widthPct));
                if (w <= 0) return null;
                return (
                  <div
                    key={`${b.label}-${bi}`}
                    title={b.label}
                    className={`absolute top-0.5 bottom-0.5 rounded-sm ${barClass(b.color)} opacity-95`}
                    style={{ left: `${start}%`, width: `${w}%` }}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
