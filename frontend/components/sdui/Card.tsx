"use client";

import type { ReactNode } from "react";

type Props = {
  title?: string;
  children?: ReactNode;
};

export function SduiCard({ title, children }: Props) {
  return (
    <div className="rounded-2xl bg-white border border-slate-100 shadow-[0_2px_12px_-4px_rgba(0,0,0,0.06)] p-6 min-w-0 transition-shadow hover:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.08)] dark:bg-zinc-900 dark:border-white/5">
      {title ? (
        <h4 className="text-base font-semibold tracking-tight text-slate-900 mb-4">{title}</h4>
      ) : null}
      <div className="min-w-0 flex flex-col gap-2">{children}</div>
    </div>
  );
}
