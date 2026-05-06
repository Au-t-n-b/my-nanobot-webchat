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
    "bg-[var(--surface-2)] text-[var(--text-secondary)] ring-1 ring-inset ring-[var(--border-subtle)]",
  success:
    "bg-[var(--success-bg)] text-[var(--success)] ring-1 ring-inset ring-[var(--success-border)]",
  warning:
    "bg-[var(--warning-bg)] text-[var(--warning)] ring-1 ring-inset ring-[var(--warning-border)]",
  danger:
    "bg-[var(--danger-bg)] text-[var(--danger-fg)] ring-1 ring-inset ring-[var(--danger-border)]",
};

export function SduiBadge({ text, label, tone = "default", color, size = "md" }: Props) {
  const display = (label ?? text ?? "").toString();
  const pad = size === "sm" ? "px-1.5 py-0.5 ui-text-eyebrow" : "px-2 py-0.5 ui-text-label";
  const cls = color ? semanticSoftBadgeClass(color) : (toneClass[tone] ?? toneClass.default);
  return (
    <span className={`inline-flex items-center rounded-lg font-medium ${pad} ${cls}`.trim()}>
      {display}
    </span>
  );
}
