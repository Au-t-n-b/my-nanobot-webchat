"use client";

import type { SduiSemanticColor } from "@/lib/sdui";
import { semanticTextClass } from "@/components/sdui/sduiSemanticColor";

type Props = {
  content?: string | null;
  variant?: "caption" | "body" | "heading" | "mono";
  color?: SduiSemanticColor;
  align?: "start" | "center" | "end";
};

const variantClass: Record<NonNullable<Props["variant"]>, string> = {
  heading: "text-base font-semibold tracking-tight text-[var(--text-primary)]",
  body: "text-sm leading-relaxed text-[var(--text-secondary)]",
  caption: "text-xs text-[var(--text-muted)]",
  mono: "text-[13px] font-mono text-[var(--text-muted)] bg-[var(--surface-2)] px-1 py-0.5 rounded",
};

const alignMap: Record<NonNullable<Props["align"]>, string> = {
  start: "text-left",
  center: "text-center",
  end: "text-right",
};

export function SduiText({ content, variant = "body", color, align = "start" }: Props) {
  const c = semanticTextClass(color);
  const a = alignMap[align] ?? "text-left";
  return (
    <p className={`${variantClass[variant] ?? variantClass.body} ${c} ${a} whitespace-pre-wrap`.trim()}>
      {content ?? ""}
    </p>
  );
}
