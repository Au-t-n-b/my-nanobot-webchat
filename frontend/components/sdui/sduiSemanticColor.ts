"use client";

import type { SduiSemanticColor } from "@/lib/sdui";

export function semanticTextClass(color?: SduiSemanticColor): string {
  switch (color) {
    case "success":
      return "text-green-600 dark:text-green-400";
    case "warning":
      return "text-yellow-600 dark:text-yellow-400";
    case "error":
      return "text-red-600 dark:text-red-400";
    case "accent":
      return "text-blue-600 dark:text-blue-400";
    case "subtle":
      return "text-slate-500 dark:text-slate-400";
    default:
      return "";
  }
}

export function semanticBgClass(color?: SduiSemanticColor): string {
  switch (color) {
    case "success":
      return "bg-green-500";
    case "warning":
      return "bg-yellow-500";
    case "error":
      return "bg-red-500";
    case "accent":
      return "bg-blue-600 dark:bg-blue-500";
    case "subtle":
      return "bg-slate-200/60 dark:bg-white/10";
    default:
      return "";
  }
}

export function semanticSoftBadgeClass(color?: SduiSemanticColor): string {
  switch (color) {
    case "success":
      return "bg-green-50 text-green-700 ring-1 ring-inset ring-green-600/10 dark:bg-green-500/10 dark:text-green-300 dark:ring-green-500/20";
    case "warning":
      return "bg-yellow-50 text-yellow-800 ring-1 ring-inset ring-yellow-600/10 dark:bg-yellow-500/10 dark:text-yellow-300 dark:ring-yellow-500/20";
    case "error":
      return "bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/10 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-500/20";
    case "accent":
      return "bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-600/10 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-500/20";
    case "subtle":
      return "bg-slate-100/90 text-slate-600 ring-1 ring-inset ring-slate-500/10 dark:bg-white/5 dark:text-zinc-300 dark:ring-white/10";
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

