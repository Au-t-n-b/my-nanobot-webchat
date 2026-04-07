"use client";

import type { SduiSemanticColor } from "@/lib/sdui";
import { semanticTextClass } from "@/components/sdui/sduiSemanticColor";

type Props = {
  title?: string | null;
  value?: string | number | null;
  color?: SduiSemanticColor;
};

export function SduiStatistic({ title, value, color }: Props) {
  const v = value === null || value === undefined ? "" : value;
  const c = semanticTextClass(color);
  return (
    <div className="min-w-0 w-full text-center">
      <div className="mb-1 text-xs font-medium text-[var(--text-muted)]">{title ?? ""}</div>
      <div className={`text-3xl font-bold tabular-nums tracking-tight text-[var(--text-primary)] ${c}`.trim()}>{v}</div>
    </div>
  );
}
