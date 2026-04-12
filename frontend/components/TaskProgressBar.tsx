"use client";

import { useMemo } from "react";

import type { RunStatus, TaskStatusPayload } from "@/hooks/useAgentChat";
import { selectProjectTaskStatus, useProjectOverviewStore } from "@/lib/projectOverviewStore";

export function TaskProgressBar({
  runStatus,
  compact = false,
  liveTaskStatus = null,
}: {
  runStatus: RunStatus;
  compact?: boolean;
  liveTaskStatus?: TaskStatusPayload | null;
}) {
  const storedTaskStatus = useProjectOverviewStore(selectProjectTaskStatus);
  const data = liveTaskStatus ?? storedTaskStatus;

  const overall = useMemo(
    () => ({
      doneCount: data?.overall.doneCount ?? 0,
      totalCount: data?.overall.totalCount ?? 0,
    }),
    [data],
  );
  const summary = useMemo(
    () =>
      data?.summary ?? {
        activeCount: runStatus === "running" || runStatus === "awaitingApproval" ? 1 : 0,
        pendingCount: 0,
        completedCount: 0,
        completionRate: 0,
      },
    [data, runStatus],
  );

  return (
    <div className={`flex items-center gap-2 select-none flex-1 min-w-0 px-2 pt-0.5 ${compact ? "pb-1" : "pb-2"}`}>
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
        </span>
        <span className="text-[10px] font-semibold tracking-widest text-slate-500 dark:text-slate-400 whitespace-nowrap">
          项目总览
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
          <span>{overall.doneCount}/{overall.totalCount} 模块完成</span>
          <span>{summary.activeCount} 运行中</span>
        </div>
        <div className="h-1.5 rounded-full overflow-hidden bg-slate-200 dark:bg-slate-700">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${summary.completionRate}%`,
              background: "linear-gradient(90deg, #10b981, #2563eb)",
            }}
          />
        </div>
        {!compact ? (
          <div className="mt-1 flex items-center gap-3 text-[10px] text-slate-400 dark:text-slate-500">
            <span>{summary.pendingCount} 待开始</span>
            <span>{summary.completedCount} 已完成</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
