"use client";

import type { ReactNode } from "react";
import type { SpacingToken } from "@/lib/sdui";
import { spacingTokenToGapPx } from "@/lib/sduiTokens";

const alignMap: Record<string, string> = {
  start: "items-start",
  center: "items-center",
  end: "items-end",
  stretch: "items-stretch",
  baseline: "items-baseline",
};

const justifyMap: Record<string, string> = {
  start: "justify-start",
  end: "justify-end",
  center: "justify-center",
  between: "justify-between",
  around: "justify-around",
};

type Props = {
  gap?: SpacingToken;
  align?: "start" | "center" | "end" | "stretch" | "baseline";
  justify?: "start" | "end" | "center" | "between" | "around";
  wrap?: boolean;
  children?: ReactNode;
};

export function SduiRow({ gap, align = "start", justify = "start", wrap = true, children }: Props) {
  const a = alignMap[align] ?? "items-start";
  const j = justifyMap[justify] ?? "justify-start";
  const px = spacingTokenToGapPx(gap);
  return (
    <div className={`flex min-w-0 ${j} ${a} ${wrap ? "flex-wrap" : "flex-nowrap"}`.trim()} style={{ gap: px }}>
      {children}
    </div>
  );
}
