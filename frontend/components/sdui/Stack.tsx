"use client";

import type { ReactNode } from "react";
import type { SpacingToken } from "@/lib/sdui";
import type { SduiStackNode } from "@/lib/sdui";

type Props = {
  gap?: SpacingToken;
  justify?: NonNullable<SduiStackNode["justify"]>;
  children?: ReactNode;
};

const gapClassMap: Record<string, string> = {
  none: "gap-0",
  xs: "gap-1",
  sm: "gap-2",
  md: "gap-3",
  lg: "gap-4",
  xl: "gap-6",
};

const justifyMap: Record<string, string> = {
  start: "justify-start",
  center: "justify-center",
  end: "justify-end",
  between: "justify-between",
};

export function SduiStack({ gap, justify = "start", children }: Props) {
  const g = gap ? (gapClassMap[gap] ?? "") : "";
  const j = justifyMap[justify] ?? "justify-start";
  return (
    <div className={`flex min-w-0 flex-col ${j} ${g}`.trim()}>
      {children}
    </div>
  );
}
