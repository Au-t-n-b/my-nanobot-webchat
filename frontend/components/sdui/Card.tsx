"use client";

import type { ReactNode } from "react";

type Props = {
  title?: string;
  /** 紧凑：更低内边距，适合产物列表等 */
  density?: "default" | "compact";
  children?: ReactNode;
};

export function SduiCard({ title, children, density = "default" }: Props) {
  const compact = density === "compact";
  return (
    <div
      className={[
        "min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[var(--paper-card)] shadow-[var(--shadow-card)] transition-shadow hover:shadow-md",
        compact ? "p-3" : "p-6",
      ].join(" ")}
    >
      {title ? (
        <h4
          className={[
            "font-semibold tracking-tight text-[var(--text-primary)]",
            compact ? "mb-2 text-sm" : "mb-4 text-base",
          ].join(" ")}
        >
          {title}
        </h4>
      ) : null}
      <div className={["min-w-0 flex flex-col", compact ? "gap-1.5" : "gap-2"].join(" ")}>{children}</div>
    </div>
  );
}
