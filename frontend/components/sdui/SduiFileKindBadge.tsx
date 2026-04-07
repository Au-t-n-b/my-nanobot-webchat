"use client";

import { FileText, File } from "lucide-react";

import type { SduiFileKind } from "@/lib/sdui";

type Props = {
  kind: SduiFileKind;
};

/** Excel 风格：绿色底；Word：蓝色底；其它中性 */
export function SduiFileKindBadge({ kind }: Props) {
  const base = "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-[0.65rem] font-bold";
  if (kind === "docx") {
    return (
      <div
        className={`${base} border-blue-500/35 bg-blue-500/10 text-blue-600 dark:border-sky-500/35 dark:bg-sky-500/10 dark:text-sky-300`}
        title="Word"
        aria-hidden
      >
        <FileText className="h-4 w-4" strokeWidth={2} />
      </div>
    );
  }
  if (kind === "xlsx") {
    return (
      <div
        className={`${base} border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:border-emerald-400/35 dark:bg-emerald-500/10 dark:text-emerald-300`}
        title="Excel"
        aria-hidden
      >
        <span className="select-none">XLS</span>
      </div>
    );
  }
  if (kind === "pdf") {
    return (
      <div
        className={`${base} border-rose-500/35 bg-rose-500/10 text-rose-600 dark:text-rose-300`}
        title="PDF"
        aria-hidden
      >
        <span className="select-none text-[10px]">PDF</span>
      </div>
    );
  }
  return (
    <div className={`${base} border-[var(--border-subtle)] bg-[var(--surface-3)] text-[var(--text-muted)]`} title="文件" aria-hidden>
      <File className="h-4 w-4" strokeWidth={2} />
    </div>
  );
}
