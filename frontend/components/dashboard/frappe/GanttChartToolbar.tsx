"use client";

import { CalendarDays, CalendarRange, CalendarSearch, CalendarSync } from "lucide-react";

import type { ProjectGanttViewMode } from "@/lib/projectGantt/frappeViewModes";

type Props = {
  mode: ProjectGanttViewMode;
  zoom: number;
  onModeChange: (mode: ProjectGanttViewMode) => void;
  onToday: () => void;
  onZoomReset: () => void;
};

const OPTIONS: Array<{ id: ProjectGanttViewMode; label: string; icon: typeof CalendarDays }> = [
  { id: "year", label: "年", icon: CalendarRange },
  { id: "month", label: "月", icon: CalendarDays },
  { id: "week", label: "周", icon: CalendarSearch },
  { id: "day", label: "日", icon: CalendarSync },
];

export function GanttChartToolbar({ mode, zoom, onModeChange, onToday, onZoomReset }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {OPTIONS.map((option) => {
          const Icon = option.icon;
          const active = option.id === mode;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => onModeChange(option.id)}
              className={[
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors",
                active
                  ? "border-[color-mix(in_srgb,var(--accent)_48%,transparent)] bg-[color-mix(in_srgb,var(--accent)_16%,transparent)] text-[var(--accent)]"
                  : "border-[var(--border-subtle)] ui-text-muted hover:bg-[var(--surface-2)] hover:ui-text-primary",
              ].join(" ")}
            >
              <Icon size={13} />
              {option.label}
            </button>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button
          type="button"
          onClick={onToday}
          className="rounded-full border border-[var(--border-subtle)] px-3 py-1.5 ui-text-muted transition-colors hover:bg-[var(--surface-2)] hover:ui-text-primary"
        >
          回到今天
        </button>
        <button
          type="button"
          onClick={onZoomReset}
          className="rounded-full border border-[var(--border-subtle)] px-3 py-1.5 ui-text-muted transition-colors hover:bg-[var(--surface-2)] hover:ui-text-primary"
        >
          缩放 {Math.round(zoom * 100)}%
        </button>
      </div>
    </div>
  );
}
