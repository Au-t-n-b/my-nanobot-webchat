"use client";

import type { ModuleEntry } from "@/components/DashboardNavigator";

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
  done: {
    badge: "bg-[color-mix(in_oklab,var(--success)_12%,transparent)] text-[var(--success)] border-[color-mix(in_oklab,var(--success)_25%,transparent)]",
    bar: "bg-[var(--success)]",
    dot: "bg-[var(--success)]",
  },
  idle: {
    badge: "bg-[var(--surface-3)] text-[var(--text-muted)] border-[var(--border-subtle)]",
    bar: "bg-[var(--surface-3)]",
    dot: "bg-[var(--text-muted)]",
  },
};

const STATUS_LABEL: Record<ModuleEntry["status"], string> = {
  running: "进行中",
  done: "已完成",
  idle: "待开始",
};

export function ProjectOverview({ modules, onSelectModule }: Props) {
  const doneCount = modules.filter((m) => m.status === "done").length;
  const pct = modules.length === 0 ? 0 : Math.round((doneCount / modules.length) * 100);

  return (
    <div className="h-full min-h-0 overflow-y-auto p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold ui-text-primary tracking-wide">项目总览</h2>
        <span className="text-xs ui-text-muted">{doneCount}/{modules.length} 模块完成</span>
      </div>

      {modules.length === 0 && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center py-16">
          <div className="text-4xl opacity-30">📊</div>
          <p className="text-sm ui-text-muted leading-relaxed">
            等待 Skill 执行…<br />
            <span className="text-xs opacity-60">Skill 启动后，模块大盘将自动出现</span>
          </p>
        </div>
      )}

      {modules.length > 0 && (
        <div className="module-cards-grid gap-3">
          {modules.map((m) => {
            const s = STATUS_STYLES[m.status];
            return (
              <button
                key={m.moduleId}
                type="button"
                onClick={() => onSelectModule(m.moduleId)}
                className="text-left rounded-xl p-3 border transition-colors hover:bg-[var(--surface-2)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]"
                style={{ background: "var(--surface-1)", borderColor: "var(--border-subtle)" }}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <span className="text-sm font-semibold ui-text-primary leading-tight">{m.label}</span>
                  <span className={`shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${s.badge}`}>
                    {m.status === "running" && (
                      <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${s.dot} animate-pulse`} />
                    )}
                    {STATUS_LABEL[m.status]}
                  </span>
                </div>
                <div className="h-1 rounded-full overflow-hidden" style={{ background: "var(--surface-3)" }}>
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${s.bar}`}
                    style={{ width: m.status === "done" ? "100%" : m.status === "running" ? "60%" : "0%" }}
                  />
                </div>
                <p className="text-[11px] ui-text-muted mt-1.5">{m.moduleId}</p>
              </button>
            );
          })}
        </div>
      )}

      {modules.length > 0 && (
        <div className="mt-auto pt-3 border-t border-[var(--border-subtle)]">
          <div className="flex justify-between text-xs ui-text-muted mb-1">
            <span>项目整体进度</span>
            <span className="font-bold" style={{ color: "var(--accent)" }}>{pct}%</span>
          </div>
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: "var(--surface-3)" }}>
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${pct}%`, background: "linear-gradient(90deg, var(--success), var(--accent))" }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
