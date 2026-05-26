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
  const pad = compact ? "var(--card-pad-compact)" : "var(--card-pad)";
  return (
    <div
      className="min-w-0 rounded-2xl border border-[var(--border-subtle)] bg-[var(--paper-card)] shadow-[var(--shadow-card)] transition-shadow hover:shadow-md"
      style={{ padding: pad }}
    >
      {title ? (
        <h4
          className={[
            "sticky top-0 z-[2] font-semibold tracking-tight text-[var(--text-primary)] supports-[backdrop-filter]:backdrop-blur-sm",
            compact ? "mb-2 text-sm" : "mb-4 text-base",
          ].join(" ")}
          style={{
            backgroundColor: "color-mix(in oklab, var(--paper-card) 88%, transparent)",
            marginInline: `calc(${pad} * -1)`,
            paddingInline: pad,
            marginTop: `calc(${pad} * -1)`,
            paddingTop: `calc(${pad} * 0.6)`,
            paddingBottom: `calc(${pad} * 0.4)`,
          }}
        >
          {title}
        </h4>
      ) : null}
      <div className="min-w-0 flex flex-col" style={{ gap: "var(--item-gap)" }}>
        {children}
      </div>
    </div>
  );
}
