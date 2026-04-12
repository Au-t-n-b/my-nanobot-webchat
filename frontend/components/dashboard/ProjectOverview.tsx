"use client";

import { useMemo } from "react";

import type { ModuleEntry } from "@/components/DashboardNavigator";
import { ProjectGanttChart } from "@/components/dashboard/ProjectGanttChart";
import { formatProjectGanttMetaLabel, getProjectGanttEstimatedDays } from "@/lib/projectGantt/presentation.js";

type Props = {
  modules: ModuleEntry[];
  onSelectModule: (id: string) => void;
};

const STATUS_STYLES: Record<ModuleEntry["status"], { badge: string; bar: string; dot: string }> = {
  running: {
    badge: "bg-[color-mix(in_oklab,var(--accent)_15%,transparent)] text-[var(--accent)] border-[color-mix(in_oklab,var(--accent)_30%,transparent)]",
    bar: "bg-[var(--accent)]",
    dot: "bg-[var(--accent)] shadow-[0_0_6px_var(--accent)]",
  },
  completed: {
    badge: "bg-[color-mix(in_oklab,var(--success)_18%,transparent)] text-[var(--success)] border-[color-mix(in_oklab,var(--success)_30%,transparent)]",
    bar: "bg-[var(--success)]",
    dot: "bg-[var(--success)] shadow-[0_0_6px_var(--success)]",
  },
  idle: {
    badge: "bg-[var(--surface-3)] text-[var(--text-muted)] border-[var(--border-subtle)]",
    bar: "bg-[var(--surface-3)]",
    dot: "bg-[var(--text-muted)]",
  },
};

const STATUS_LABEL: Record<ModuleEntry["status"], string> = {
  running: "进行中",
  completed: "已完成",
  idle: "待命",
};

export function ProjectOverview({ modules, onSelectModule }: Props) {
  const runningCount = modules.filter((item) => item.status === "running").length;
  const completedCount = modules.filter((item) => item.status === "completed").length;
  const pendingCount = Math.max(0, modules.length - runningCount - completedCount);
  const completionPct = modules.length ? Math.round((completedCount / modules.length) * 100) : 0;

  const workbenchModule = useMemo(
    () => modules.find((item) => item.label === "智能分析工作台") ?? null,
    [modules],
  );

  return (
    <div className="h-full min-h-0 overflow-y-auto p-5 flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold ui-text-primary tracking-wide">项目总览</h2>
        <span className="text-xs ui-text-muted">
          {runningCount}/{modules.length} 模块活跃
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="ui-elevated-card p-5">
          <p className="text-[11px] ui-text-muted">项目完成度</p>
          <p className="mt-2 text-2xl font-semibold ui-text-primary">{completionPct}%</p>
          <p className="text-[11px] ui-text-muted">{completedCount} 个模块完成</p>
        </div>
        <div className="ui-elevated-card p-5">
          <p className="text-[11px] ui-text-muted">任务活跃态</p>
          <p className="mt-2 text-2xl font-semibold ui-text-primary">{runningCount}</p>
          <p className="text-[11px] ui-text-muted">运行中 / {pendingCount} 待开始</p>
        </div>
      </div>

      {workbenchModule ? (
        <button
          type="button"
          onClick={() => onSelectModule(workbenchModule.moduleId)}
          className="ui-elevated-card p-5 text-left transition-colors hover:bg-[var(--surface-2)]"
        >
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-base font-semibold ui-text-primary">进入智能分析工作台</p>
              <p className="mt-2 text-[12px] ui-text-muted">
                当前项目阶段：{workbenchModule.progressLabel ?? "待开始"}
              </p>
            </div>
            <span className="rounded-full bg-[color-mix(in_srgb,var(--accent)_16%,transparent)] px-3 py-1 text-xs text-[var(--accent)]">
              打开大盘
            </span>
          </div>
        </button>
      ) : null}

      {modules.length > 0 ? (
        <div className="ui-elevated-card p-6">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-xs font-semibold ui-text-primary">项目阶段进展</h3>
            <span className="text-[11px] ui-text-muted">
              {completedCount}/{modules.length}
            </span>
          </div>
          <div className="mb-4 flex flex-wrap items-center gap-3 text-[11px] ui-text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--success)]" />
              已完成
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--accent)]" />
              进行中
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--surface-3)] border border-[var(--border-subtle)]" />
              待开始
            </span>
          </div>
          <div className="space-y-3">
            <ProjectGanttChart modules={modules} onSelectModule={onSelectModule} />
            <div className="space-y-2.5">
              {modules.map((module) => {
                const doneCount = module.steps?.filter((step) => step.done).length ?? 0;
                const totalCount = module.steps?.length ?? 0;
                const metaLabel = formatProjectGanttMetaLabel({
                  estimatedDays: getProjectGanttEstimatedDays(totalCount),
                  isPlaceholder: module.isPlaceholder,
                });
                return (
                  <div key={module.moduleId} className="flex items-center justify-between gap-3 text-[11px]">
                    <span className="min-w-0 flex items-center gap-2">
                      <span className="ui-text-primary truncate">{module.label}</span>
                      {module.isPlaceholder ? (
                        <span className="shrink-0 rounded-full border border-dashed border-white/12 bg-white/[0.04] px-2 py-0.5 text-[10px] ui-text-muted">
                          规划中
                        </span>
                      ) : null}
                    </span>
                    <span className="shrink-0 ui-text-muted">
                      {[metaLabel, module.progressLabel ?? "待开始", `${doneCount}/${totalCount}`].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}

      {modules.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center py-16">
          <div className="text-2xl font-semibold tracking-[0.3em] opacity-30">PLAN</div>
          <p className="text-sm ui-text-muted leading-relaxed">
            等待 Skill 执行…<br />
            <span className="text-xs opacity-60">Skill 启动后，模块大盘将自动出现</span>
          </p>
        </div>
      )}

      {modules.length > 0 && (
        <div className="module-cards-grid gap-3">
          {modules.map((module) => {
            const style = STATUS_STYLES[module.status];
            return (
              <button
                key={module.moduleId}
                type="button"
                onClick={() => {
                  if (module.isPlaceholder) return;
                  onSelectModule(module.moduleId);
                }}
                className={[
                  "ui-elevated-card text-left p-5 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]",
                  module.isPlaceholder ? "opacity-80 cursor-default" : "hover:bg-[var(--surface-2)]",
                ].join(" ")}
              >
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className="text-sm font-semibold ui-text-primary leading-tight">{module.label}</span>
                    {module.description ? (
                      <p className="mt-2 text-[11px] ui-text-muted line-clamp-2">{module.description}</p>
                    ) : null}
                  </div>
                  <span className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${style.badge}`}>
                    {module.isPlaceholder && module.status === "idle" ? "规划中" : null}
                    {module.status === "running" && (
                      <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${style.dot} animate-pulse`} />
                    )}
                    {module.isPlaceholder && module.status === "idle" ? null : STATUS_LABEL[module.status]}
                  </span>
                </div>
                <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--surface-3)" }}>
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${style.bar}`}
                    style={{ width: `${module.progressPct ?? (module.status === "completed" ? 100 : 0)}%` }}
                  />
                </div>
                <p className="mt-2 text-[11px] ui-text-muted">
                  {[formatProjectGanttMetaLabel({
                    estimatedDays: getProjectGanttEstimatedDays(module.steps?.length ?? 0),
                    isPlaceholder: module.isPlaceholder,
                  }), module.progressLabel ?? module.moduleId]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </button>
            );
          })}
        </div>
      )}

      {modules.length > 0 && (
        <div className="mt-auto pt-3 border-t border-[var(--border-subtle)]">
          <div className="flex justify-between text-xs ui-text-muted mb-1">
            <span>模块完成占比</span>
            <span className="font-bold" style={{ color: "var(--accent)" }}>{completionPct}%</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--surface-3)" }}>
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${completionPct}%`, background: "linear-gradient(90deg, var(--success), var(--accent))" }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
