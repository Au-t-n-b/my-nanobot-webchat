"use client";

import type { ReactNode } from "react";
import type { SpacingToken } from "@/lib/sdui";
import { spacingTokenToGapPx } from "@/lib/sduiTokens";

type Props = {
  gap?: SpacingToken;
  children?: ReactNode;
};

export function SduiStack({ gap, children }: Props) {
  const px = spacingTokenToGapPx(gap);
  return (
    <div className="flex flex-col min-w-0" style={{ gap: px }}>
      {children}
    </div>
  );
}
