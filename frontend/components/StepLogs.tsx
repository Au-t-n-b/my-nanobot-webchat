"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import type { RunStatus, StepLog } from "@/hooks/useAgentChat";
import { CheckCircle2, ChevronRight, CircleDashed, ShieldAlert, TriangleAlert } from "lucide-react";

type Props = {
  stepLogs: StepLog[];
  runStatus: RunStatus;
  statusMessage: string;
  runModel?: string | null;
  /** 等待模型流式响应时为胶囊加微弱扫光 */
  isLoading?: boolean;
  /** 混合模式：受控 Agent 子任务（TaskStatus 中 `hybrid:*` 模块） */
  hybridSubtaskHint?: string | null;
};

function statusMeta(runStatus: RunStatus): { label: string; className: string; icon: ReactNode } {
  switch (runStatus) {
    case "running":
      return { label: "执行中", className: "ui-status-running", icon: <CircleDashed size={12} className="animate-spin" /> };
    case "awaitingApproval":
      return { label: "等待确认", className: "ui-status-warning", icon: <ShieldAlert size={12} /> };
    case "completed":
      return { label: "已完成", className: "ui-status-success", icon: <CheckCircle2 size={12} /> };
    case "error":
      return { label: "失败", className: "ui-status-danger", icon: <TriangleAlert size={12} /> };
    default:
      return { label: "待命", className: "ui-text-muted", icon: <CircleDashed size={12} /> };
  }
}

/** 单行状态胶囊：降噪；完成后 3s 自动收起文案，把纵向空间还给对话 */
export function StepLogs({
  stepLogs,
  runStatus,
  statusMessage,
  runModel,
  isLoading = false,
  hybridSubtaskHint = null,
}: Props) {
  const [open, setOpen] = useState(false);
  const [autoCompact, setAutoCompact] = useState(false);

  useEffect(() => {
    if (runStatus !== "completed") {
      setAutoCompact(false);
      return;
    }
    const id = window.setTimeout(() => setAutoCompact(true), 3000);
    return () => window.clearTimeout(id);
  }, [runStatus, statusMessage]);

  if (!stepLogs.length && runStatus === "idle" && !hybridSubtaskHint) return null;

  const meta = statusMeta(runStatus);
  const hasLogs = stepLogs.length > 0;
  const hideEntirely =
    runStatus === "completed" && autoCompact && !hasLogs && !open && !hybridSubtaskHint;

  if (hideEntirely) return null;

  const showMessageLine =
    runStatus !== "completed" || !autoCompact || open || !hasLogs;

  const shimmer = Boolean(isLoading && (runStatus === "running" || runStatus === "idle"));

  return (
    <div className="shrink-0 space-y-2">
      <div
        className={
          "relative flex flex-wrap items-center gap-x-2 gap-y-0.5 overflow-hidden rounded-full border px-3 py-1.5 text-[11px] leading-tight transition-all duration-300 " +
          "border-[color-mix(in_oklab,var(--border-subtle)_90%,transparent)] " +
          "bg-[color-mix(in_oklab,var(--surface-1)_75%,transparent)] backdrop-blur-md " +
          (autoCompact && runStatus === "completed" && hasLogs && !open ? "py-1" : "") +
          (shimmer ? " nanobot-status-pill-shimmer" : "")
        }
      >
        <span className={`inline-flex shrink-0 ${meta.className}`} aria-hidden>
          {meta.icon}
        </span>
        <span className={`font-medium shrink-0 ${meta.className}`}>{meta.label}</span>
        {showMessageLine ? (
          <>
            <span className="text-[var(--text-muted)] shrink-0">:</span>
            <span className="text-[var(--text-secondary)] truncate min-w-0 max-w-[min(100%,28rem)]">
              {statusMessage}
            </span>
            {runModel ? (
              <span className="text-[var(--text-muted)] shrink-0 tabular-nums opacity-80">
                ({runModel})
              </span>
            ) : null}
          </>
        ) : null}

        {hasLogs ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="ml-auto inline-flex items-center gap-0.5 shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            {open ? "收起" : "查看详情"}
            <ChevronRight size={12} className={open ? "rotate-90 transition-transform" : "transition-transform"} />
          </button>
        ) : null}
      </div>

      {open && hasLogs && (
        <ul className="space-y-1 max-h-40 overflow-y-auto text-[11px] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]/50 px-2 py-2">
          {stepLogs.map((s) => (
            <li key={s.id} className="ui-subtle rounded-md px-2 py-1.5 ui-text-secondary">
              <span className="ui-text-muted mr-2">
                [{s.stepName === "tool" ? "工具" : "分析"}]
              </span>
              {s.text}
            </li>
          ))}
        </ul>
      )}

      {hybridSubtaskHint ? (
        <div
          className={
            "flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-lg border px-3 py-1.5 text-[10px] leading-tight " +
            "border-[color-mix(in_oklab,var(--border-subtle)_90%,transparent)] " +
            "bg-[color-mix(in_oklab,var(--surface-2)_55%,transparent)] text-[var(--text-secondary)]"
          }
        >
          <span className="shrink-0 font-semibold tracking-wide text-[var(--text-muted)]">Agent 子任务</span>
          <span className="min-w-0 truncate max-w-[min(100%,28rem)]">{hybridSubtaskHint}</span>
        </div>
      ) : null}
    </div>
  );
}
