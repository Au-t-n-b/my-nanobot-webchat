"use client";

import type { SduiSemanticColor } from "@/lib/sdui";
import { semanticSoftBadgeClass } from "@/components/sdui/sduiSemanticColor";

type Props = {
  text?: string | null;
  tone?: "default" | "success" | "warning" | "danger";
  label?: string | null;
  color?: SduiSemanticColor;
  size?: "sm" | "md";
};

const toneClass: Record<NonNullable<Props["tone"]>, string> = {
  default:
    "bg-slate-100/90 text-slate-600 ring-1 ring-inset ring-slate-500/10 dark:bg-white/5 dark:text-[var(--text-secondary)] dark:ring-white/10",
  success:
    "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/10 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20",
  warning:
    "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/10 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20",
  danger:
    "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/10 dark:bg-red-500/10 dark:text-red-400 dark:ring-red-500/20",
};

export function SduiBadge({ text, label, tone = "default", color, size = "md" }: Props) {
  const display = (label ?? text ?? "").toString();
  const pad = size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]";
  const cls = color ? semanticSoftBadgeClass(color) : (toneClass[tone] ?? toneClass.default);
  return (
    <span className={`inline-flex items-center rounded-md font-medium ${pad} ${cls}`.trim()}>
      {display}
    </span>
  );
}
