"use client";

import type { ModuleEntry } from "@/components/DashboardNavigator";

type Props = {
  modules: ModuleEntry[];
  onSelectModule: (id: string) => void;
};

export function ProjectOverview({ modules, onSelectModule }: Props) {
  void onSelectModule;
  const runningCount = modules.filter((item) => item.status === "running").length;
  const completedCount = modules.filter((item) => item.status === "completed").length;
  const pendingCount = Math.max(0, modules.length - runningCount - completedCount);
  const completionPct = modules.length ? Math.round((completedCount / modules.length) * 100) : 0;

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
