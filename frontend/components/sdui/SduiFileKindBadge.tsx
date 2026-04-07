"use client";

import { FileCode, FileText, File } from "lucide-react";

import type { SduiFileKind } from "@/lib/sdui";

type Props = {
  kind: SduiFileKind;
  size?: "default" | "lg";
};

/** Excel 风格：绿色底；Word：蓝色底；其它中性 */
export function SduiFileKindBadge({ kind, size = "default" }: Props) {
  const lg = size === "lg";
  const base = [
    "flex shrink-0 items-center justify-center rounded-lg border font-bold",
    lg ? "h-11 w-11 text-sm" : "h-9 w-9 text-[0.65rem]",
  ].join(" ");
  if (kind === "docx") {
    return (
      <div
        className={`${base} border-[color-mix(in_oklab,#2563eb_38%,var(--border-subtle))] bg-[color-mix(in_oklab,#2563eb_12%,var(--surface-2))] text-[color-mix(in_oklab,#1d4ed8_90%,var(--text-primary))] dark:border-[color-mix(in_oklab,#38bdf8_40%,var(--border-subtle))] dark:bg-[color-mix(in_oklab,#38bdf8_12%,var(--surface-2))] dark:text-[color-mix(in_oklab,#7dd3fc_90%,var(--text-primary))]`}
        title="Word"
        aria-hidden
      >
        <FileText className={lg ? "h-5 w-5" : "h-4 w-4"} strokeWidth={2} />
      </div>
    );
  }
  if (kind === "xlsx") {
    return (
      <div
        className={`${base} border-[color-mix(in_oklab,#059669_40%,var(--border-subtle))] bg-[color-mix(in_oklab,#059669_12%,var(--surface-2))] text-[color-mix(in_oklab,#047857_92%,var(--text-primary))] dark:border-[color-mix(in_oklab,#34d399_38%,var(--border-subtle))] dark:bg-[color-mix(in_oklab,#34d399_12%,var(--surface-2))] dark:text-[color-mix(in_oklab,#6ee7b7_92%,var(--text-primary))]`}
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
        className={`${base} border-[color-mix(in_oklab,var(--danger)_35%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--danger)_12%,var(--surface-2))] text-[color-mix(in_oklab,var(--danger)_85%,var(--text-primary))]`}
        title="PDF"
        aria-hidden
      >
        <span className={`select-none ${lg ? "text-xs" : "text-[10px]"}`}>PDF</span>
      </div>
    );
  }
  if (kind === "html") {
    return (
      <div
        className={`${base} border-[color-mix(in_oklab,var(--accent)_40%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--accent-soft)_100%,var(--surface-2))] text-[var(--accent)]`}
        title="HTML"
        aria-hidden
      >
        <FileCode className={lg ? "h-5 w-5" : "h-4 w-4"} strokeWidth={2} />
      </div>
    );
  }
  return (
    <div className={`${base} border-[var(--border-subtle)] bg-[var(--surface-3)] text-[var(--text-muted)]`} title="文件" aria-hidden>
      <File className={lg ? "h-5 w-5" : "h-4 w-4"} strokeWidth={2} />
    </div>
  );
}
