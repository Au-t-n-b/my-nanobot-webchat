"use client";

import type { ReactNode } from "react";

type Props = {
  title?: string;
  children?: ReactNode;
};

export function SduiCard({ title, children }: Props) {
  return (
    <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--paper-card)] p-6 min-w-0 shadow-[var(--shadow-card)] transition-shadow hover:shadow-md">
      {title ? (
        <h4 className="mb-4 text-base font-semibold tracking-tight text-[var(--text-primary)]">{title}</h4>
      ) : null}
      <div className="min-w-0 flex flex-col gap-2">{children}</div>
    </div>
  );
}
