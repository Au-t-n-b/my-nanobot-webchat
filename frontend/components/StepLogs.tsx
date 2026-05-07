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
  /** 待授权时：滚动到工具确认卡片 */
  onViewPendingTool?: () => void;
  /** 执行失败后重试（如重发上轮用户消息） */
  onRetryAfterError?: () => void;
  /** 复制错误文案 */
  onCopyErrorText?: () => void;
  /** 将焦点给模型行 / 由上层处理 */
  onRequestSwitchModel?: () => void;
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

function formatElapsed(ms: number): string {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m${s.toString().padStart(2, "0")}s`;
}

function simplifyStepText(raw: string): string {
  const s = (raw ?? "").trim();
  if (!s) return "";
  // Drop redundant macro stats like "2/5 完成：..." or "2/5 完成 ..." which are already shown by global stepper.
  const withoutMacro = s.replace(/^\s*\d+\s*\/\s*\d+\s*(完成|done)\s*[:：\-\u00b7]?\s*/i, "");
  // Normalize separators for breathing room.
  return withoutMacro.replace(/\s*[:：]\s*/g, " · ").replace(/\s{2,}/g, " ").trim();
}

/** 单行状态胶囊：降噪；完成后 3s 自动收起文案，把纵向空间还给对话 */
export function StepLogs({
  stepLogs,
  runStatus,
  statusMessage,
  runModel,
  isLoading = false,
  hybridSubtaskHint = null,
  onViewPendingTool,
  onRetryAfterError,
  onCopyErrorText,
  onRequestSwitchModel,
}: Props) {
  const [open, setOpen] = useState(false);
  const [autoCompact, setAutoCompact] = useState(false);
  const [runStartAt, setRunStartAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [frozenElapsedMs, setFrozenElapsedMs] = useState<number | null>(null);

  useEffect(() => {
    if (runStatus !== "completed") {
      setAutoCompact(false);
      return;
    }
    const id = window.setTimeout(() => setAutoCompact(true), 3000);
    return () => window.clearTimeout(id);
  }, [runStatus, statusMessage]);

  // Track elapsed time for the pill: running/awaitingApproval live updates; completed/error freezes.
  useEffect(() => {
    if (runStatus === "running" || runStatus === "awaitingApproval") {
      setFrozenElapsedMs(null);
      setRunStartAt((prev) => prev ?? Date.now());
      return;
    }
    setRunStartAt(null);
    setElapsedMs(0);
    if (runStatus === "completed" || runStatus === "error") {
      setFrozenElapsedMs((prev) => prev ?? elapsedMs);
    }
  }, [runStatus, elapsedMs]);

  useEffect(() => {
    if (!runStartAt) return;
    const tick = () => setElapsedMs(Date.now() - runStartAt);
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [runStartAt]);

  if (!stepLogs.length && runStatus === "idle" && !hybridSubtaskHint) return null;

  const meta = statusMeta(runStatus);
  const hasLogs = stepLogs.length > 0;
  const hideEntirely =
    runStatus === "completed" && autoCompact && !hasLogs && !open && !hybridSubtaskHint;

  if (hideEntirely) return null;

  const showMessageLine =
    runStatus !== "completed" || !autoCompact || open || !hasLogs;

  const shimmer = Boolean(isLoading && (runStatus === "running" || runStatus === "idle"));

  const isApproval = runStatus === "awaitingApproval";
  const isErr = runStatus === "error";
  const useApprovalUi = isApproval;
  const useErrorUi = isErr;

  const stepText = simplifyStepText(statusMessage);
  const elapsedLabel = formatElapsed(frozenElapsedMs ?? elapsedMs);

  return (
    <div className="shrink-0 space-y-2">
      {useApprovalUi ? (
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              const el = document.getElementById("nanobot-pending-tool");
              if (el) {
                el.scrollIntoView({ behavior: "smooth", block: "center" });
                return;
              }
              if (onViewPendingTool) return onViewPendingTool();
              console.log("[StepLogs] pending tool: scrollIntoView placeholder");
            }}
            className={
              "relative flex w-full flex-wrap items-center gap-x-2 gap-y-0.5 overflow-hidden rounded-full border px-3 py-2 text-[11px] leading-tight " +
              "border-[color-mix(in_oklab,var(--accent)_25%,var(--border-subtle))] bg-[var(--accent-soft)] text-[var(--text-primary)] " +
              "ring-1 ring-[color-mix(in_oklab,var(--accent)_30%,transparent)] " +
              "transition-[transform,background,border] duration-200 ease-out hover:brightness-[1.02] active:scale-[0.995] " +
              "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-[var(--accent)] " +
              (shimmer ? " nanobot-status-pill-shimmer" : "")
            }
            aria-label="查看要授权的工具"
            title="查看要授权的工具"
          >
            <span className="inline-flex shrink-0 text-amber-500" aria-hidden>
              {meta.icon}
            </span>
            <span className="font-semibold shrink-0 text-amber-500">⚠️ 查看要授权的工具</span>
            {showMessageLine ? (
              <>
                {stepText ? <span className="text-[var(--text-muted)] shrink-0">·</span> : null}
                {stepText ? (
                  <span className="text-[var(--text-secondary)] truncate min-w-0 max-w-[min(100%,26rem)]">
                    {stepText}
                  </span>
                ) : null}
                {runModel ? <span className="text-[var(--text-muted)] shrink-0">·</span> : null}
                {runModel ? (
                  <span className="text-[var(--text-muted)] shrink-0 tabular-nums opacity-85">
                    {runModel}
                  </span>
                ) : null}
                <span className="text-[var(--text-muted)] shrink-0">·</span>
                <span className="text-[var(--text-muted)] shrink-0 tabular-nums opacity-85">{elapsedLabel}</span>
              </>
            ) : null}
            {hasLogs ? (
              <span className="ml-auto inline-flex items-center gap-0.5 shrink-0 text-[var(--text-muted)]">
                {open ? "收起" : "详情"}
                <ChevronRight size={12} className={open ? "rotate-90 transition-transform duration-200" : "transition-transform duration-200"} />
              </span>
            ) : null}
          </button>
          {hasLogs ? (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="sr-only"
              aria-label={open ? "收起步骤详情" : "展开步骤详情"}
            />
          ) : null}
        </div>
      ) : useErrorUi ? (
        <div
          className={
            "relative flex flex-wrap items-center gap-x-2 gap-y-1 overflow-hidden rounded-2xl border px-3 py-2 text-[11px] leading-tight " +
            "border-red-500/20 bg-red-500/10 text-red-400 ring-1 ring-red-500/20 " +
            (shimmer ? " nanobot-status-pill-shimmer" : "")
          }
        >
          <span className={`inline-flex shrink-0 ${meta.className}`} aria-hidden>
            {meta.icon}
          </span>
          <span className="font-semibold shrink-0 text-red-400">错误</span>
          {showMessageLine ? (
            <>
              {stepText ? <span className="text-red-300/60 shrink-0">·</span> : null}
              {stepText ? (
                <span className="min-w-0 max-w-full flex-1 text-red-200/90 sm:max-w-[20rem] sm:truncate sm:[display:-webkit-box] sm:[-webkit-line-clamp:2] sm:[-webkit-box-orient:vertical] break-words">
                  {stepText}
                </span>
              ) : null}
              {runModel ? <span className="text-red-300/60 shrink-0">·</span> : null}
              {runModel ? <span className="shrink-0 tabular-nums text-red-300/80">{runModel}</span> : null}
              <span className="text-red-300/60 shrink-0">·</span>
              <span className="shrink-0 tabular-nums text-red-300/80">{elapsedLabel}</span>
            </>
          ) : null}

          <div className="w-full flex flex-wrap items-center justify-end gap-1 pt-0.5">
            <button
              type="button"
              onClick={() => (onRetryAfterError ? onRetryAfterError() : console.log("[StepLogs] retry placeholder"))}
              className="rounded-full border border-white/10 bg-transparent px-2 py-0.5 text-[10px] font-medium text-red-200/90 transition-colors hover:bg-white/[0.06] focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-400/60"
            >
              重试
            </button>
            <button
              type="button"
              onClick={() => {
                if (onCopyErrorText) return onCopyErrorText();
                if (typeof navigator !== "undefined" && navigator.clipboard) {
                  void navigator.clipboard.writeText(statusMessage ?? "");
                  return;
                }
                console.log("[StepLogs] copy placeholder");
              }}
              className="rounded-full border border-white/10 bg-transparent px-2 py-0.5 text-[10px] font-medium text-red-200/90 transition-colors hover:bg-white/[0.06]"
            >
              复制
            </button>
            <button
              type="button"
              onClick={() => (onRequestSwitchModel ? onRequestSwitchModel() : console.log("[StepLogs] switch model placeholder"))}
              className="rounded-full border border-white/10 bg-transparent px-2 py-0.5 text-[10px] font-medium text-red-200/90 transition-colors hover:bg-white/[0.06]"
            >
              切换模型
            </button>
            {hasLogs ? (
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="ml-auto inline-flex items-center gap-0.5 pl-1 text-[10px] text-red-200/70 hover:text-red-100 transition-colors"
              >
                {open ? "收起" : "详情"}
                <ChevronRight size={12} className={open ? "rotate-90 transition-transform duration-200" : "transition-transform duration-200"} />
              </button>
            ) : null}
          </div>
        </div>
      ) : (
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
              <span className="text-[var(--text-muted)] shrink-0">·</span>
              {stepText ? (
                <span className="text-[var(--text-secondary)] truncate min-w-0 max-w-[min(100%,22rem)]">
                  {stepText}
                </span>
              ) : null}
              {runModel ? <span className="text-[var(--text-muted)] shrink-0">·</span> : null}
              {runModel ? <span className="text-[var(--text-muted)] shrink-0 tabular-nums opacity-80">{runModel}</span> : null}
              <span className="text-[var(--text-muted)] shrink-0">·</span>
              <span className="text-[var(--text-muted)] shrink-0 tabular-nums opacity-80">{elapsedLabel}</span>
            </>
          ) : null}

          {hasLogs ? (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="ml-auto inline-flex items-center gap-0.5 shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              {open ? "收起" : "查看详情"}
              <ChevronRight
                size={12}
                className={open ? "rotate-90 transition-transform" : "transition-transform"}
              />
            </button>
          ) : null}
        </div>
      )}

      {open && hasLogs && (
        <ul className="space-y-1 max-h-40 overflow-y-auto text-[11px] rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)]/50 px-2 py-2">
          {stepLogs.map((s) => (
            <li key={s.id} className="ui-subtle rounded-md px-2 py-1.5 ui-text-secondary">
              <span className="ui-text-muted mr-2">[{s.stepName === "tool" ? "工具" : "分析"}]</span>
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
