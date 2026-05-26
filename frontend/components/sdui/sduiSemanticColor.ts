"use client";

import type { SduiSemanticColor } from "@/lib/sdui";

export function semanticTextClass(color?: SduiSemanticColor): string {
  switch (color) {
    case "success":
      return "text-[var(--success)]";
    case "warning":
      return "text-[var(--warning)]";
    case "error":
      return "text-[var(--danger)]";
    case "accent":
      return "text-[var(--accent)]";
    case "subtle":
      return "ui-text-muted";
    default:
      return "";
  }
}

export function semanticBgClass(color?: SduiSemanticColor): string {
  switch (color) {
    case "success":
      return "bg-[var(--success)]";
    case "warning":
      return "bg-[var(--warning)]";
    case "error":
      return "bg-[var(--danger)]";
    case "accent":
      return "bg-[var(--accent)]";
    case "subtle":
      return "bg-[var(--surface-3)]";
    default:
      return "";
  }
}

export function semanticSoftBadgeClass(color?: SduiSemanticColor): string {
  switch (color) {
    case "success":
      return "bg-[var(--success-bg)] text-[var(--success)] ring-1 ring-inset ring-[var(--success-border)]";
    case "warning":
      return "bg-[var(--warning-bg)] text-[var(--warning)] ring-1 ring-inset ring-[var(--warning-border)]";
    case "error":
      return "bg-[var(--danger-bg)] text-[var(--danger-fg)] ring-1 ring-inset ring-[var(--danger-border)]";
    case "accent":
      return "bg-[var(--accent-bg-soft)] text-[var(--accent)] ring-1 ring-inset ring-[var(--accent-border)]";
    case "subtle":
      return "bg-[var(--surface-2)] text-[var(--text-secondary)] ring-1 ring-inset ring-[var(--border-subtle)]";
    default:
      return "";
  }
}

/** SVG fill/stroke 可用的颜色值（不依赖主题 accent 变量，暗色也保持蓝色科技感） */
export function semanticToCssColorValue(color?: SduiSemanticColor): string | null {
  switch (color) {
    case "success":
      return "var(--sdui-success)";
    case "warning":
      return "var(--sdui-warning)";
    case "error":
      return "var(--sdui-error)";
    case "accent":
      return "var(--sdui-accent-blue)";
    case "subtle":
      return "var(--sdui-subtle)";
    default:
      return null;
  }
}

export function isSemanticColor(v: unknown): v is SduiSemanticColor {
  return v === "success" || v === "warning" || v === "error" || v === "accent" || v === "subtle";
}

