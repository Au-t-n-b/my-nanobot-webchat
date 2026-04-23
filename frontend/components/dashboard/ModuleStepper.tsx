"use client";

import type { ProjectOverviewModuleView } from "@/lib/projectOverviewStore";
import { Check } from "lucide-react";

type StepTone = "completed" | "running" | "idle";

type Props = {
  modules: ProjectOverviewModuleView[];
  activeModuleId?: string | null;
  onSelectModule?: (id: string) => void;
  className?: string;
};

function toneOf(m: ProjectOverviewModuleView, activeModuleId?: string | null): StepTone {
  if ((activeModuleId ?? "") && m.moduleId === activeModuleId) return "running";
  if (m.status === "completed") return "completed";
  if (m.status === "running") return "running";
  return "idle";
}

function pctOf(m: ProjectOverviewModuleView): number {
  if (typeof m.progressPct === "number") return Math.max(0, Math.min(100, m.progressPct));
  if (m.totalCount > 0) return Math.round((m.doneCount / m.totalCount) * 100);
  return m.status === "completed" ? 100 : 0;
}

function cleanLabel(raw: string, moduleId: string): string {
  let s = String(raw ?? "").trim();
  if (!s) return moduleId;
  // Drop parenthetical noise: "(zhgk)" / "（zhgk）" / "(模块大盘)" etc.
  s = s.replace(/[（(][^）)]*[)）]/g, "");
  // Drop common suffix noise.
  s = s.replace(/大盘/g, "");
  s = s.replace(/模块/g, "");
  s = s.replace(/\s+/g, " ").trim();
  return s || moduleId;
}

const TONE = {
  completed: {
    dot: "bg-emerald-500",
    ring: "ring-emerald-500/25",
    rail: "bg-emerald-500",
    text: "text-zinc-300",
    chip: "bg-emerald-500/20 text-emerald-500 border-emerald-500/30",
  },
  running: {
    dot: "bg-amber-500",
    ring: "ring-amber-500/25",
    rail: "bg-zinc-700",
    text: "text-white font-semibold",
    chip: "bg-amber-500/20 text-amber-500 border-amber-500/30",
  },
  idle: {
    dot: "bg-transparent border border-zinc-700",
    ring: "ring-zinc-800/40",
    rail: "bg-zinc-700",
    text: "text-zinc-500",
    chip: "bg-zinc-700/20 text-zinc-400 border-zinc-700/30",
  },
} as const satisfies Record<StepTone, Record<string, string>>;

export function ModuleStepper({
  modules,
  activeModuleId = null,
  onSelectModule,
  className,
}: Props) {
  const clickable = Boolean(onSelectModule);
  return (
    <section className={["px-2 w-full min-w-0 max-w-full", className].filter(Boolean).join(" ")}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold tracking-widest text-slate-500 dark:text-slate-400">
          流程进度
        </span>
        <span className="text-[11px] ui-text-muted tabular-nums">
          {modules.filter((m) => m.status === "completed").length}/{modules.length}
        </span>
      </div>

      <div className="mt-2 w-full min-w-0 max-w-full rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] overflow-visible">
        <div className="relative px-3 py-3 min-w-0">
            <ol className="flex items-start w-full" role="list" aria-label="阶段进展">
            {modules.map((m, idx) => {
              const tone = toneOf(m, activeModuleId);
              const pct = pctOf(m);
              const isDisabled = Boolean(m.isPlaceholder) || !clickable;
              const isActive = (activeModuleId ?? "") && m.moduleId === activeModuleId;
              const label = cleanLabel(m.label, m.moduleId);

              return (
                <li key={m.moduleId} className="relative flex-1 min-w-0" role="listitem">
                  {/* 贯穿连线：从当前圆心向右发射，连接到下一个圆心 */}
                  {idx < modules.length - 1 ? (
                    <div
                      className={["absolute top-[22px] left-1/2 w-full h-[2px] overflow-hidden", tone === "completed" ? TONE.completed.rail : TONE.idle.rail].join(" ")}
                      style={{ zIndex: 0, transition: "background-color 240ms ease" }}
                      aria-hidden="true"
                    >
                      {tone === "completed" ? (
                        <span
                          className="absolute inset-0 bg-gradient-to-r from-transparent via-white/35 to-transparent"
                          style={{ transform: "translateX(-120%)", animation: "module-stepper-shimmer 2.2s ease-in-out infinite" }}
                          aria-hidden="true"
                        />
                      ) : null}
                    </div>
                  ) : null}
                    <button
                      type="button"
                      aria-disabled={isDisabled}
                      onClick={() => onSelectModule?.(m.moduleId)}
                      className={[
                        "relative z-10 group w-full rounded-xl px-2.5 py-2 transition-colors",
                        isDisabled
                          ? "opacity-80 cursor-default"
                          : "hover:bg-[var(--surface-2)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)]",
                        isActive ? "ring-1 ring-[color-mix(in_oklab,var(--accent)_30%,transparent)]" : "",
                      ].join(" ")}
                      aria-label={label}
                    >
                      <div className="flex flex-col items-center gap-1">
                        <span className="relative inline-flex h-7 w-7 items-center justify-center">
                          {/* mask background so connector never shows through the circle */}
                          <span className="absolute inset-0 rounded-full bg-[var(--surface-1)] z-10" aria-hidden="true" />
                          {tone === "completed" ? (
                            <span
                              className={[
                                "relative z-20 inline-flex h-6 w-6 items-center justify-center rounded-full ring-4",
                                "bg-emerald-500 text-white",
                                TONE.completed.ring,
                              ].join(" ")}
                              aria-hidden="true"
                            >
                              <Check size={14} strokeWidth={3} />
                            </span>
                          ) : tone === "running" ? (
                            <span
                              className={[
                                "relative z-20 inline-flex h-6 w-6 items-center justify-center rounded-full ring-4",
                                "bg-transparent border-2 border-amber-500 text-amber-500",
                                TONE.running.ring,
                              ].join(" ")}
                              aria-hidden="true"
                            >
                              <span className="relative inline-flex h-2.5 w-2.5">
                                <span className="absolute inline-flex h-full w-full rounded-full bg-amber-500 opacity-30 animate-ping" />
                                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-500" />
                              </span>
                            </span>
                          ) : (
                            <span
                              className={[
                                "relative z-20 inline-flex h-6 w-6 items-center justify-center rounded-full ring-4",
                                "bg-transparent border-2 border-zinc-700",
                                TONE.idle.ring,
                              ].join(" ")}
                              aria-hidden="true"
                            >
                              <span className="h-1.5 w-1.5 rounded-full bg-zinc-700" />
                            </span>
                          )}
                        </span>

                        <div className="w-full min-w-0 text-center">
                          <div className="w-full min-w-0">
                            <div className={["text-xs font-semibold truncate text-center", tone === "idle" ? "text-zinc-200/90" : TONE[tone].text].join(" ")}>
                              {label}
                            </div>
                            <div className="mt-1 flex justify-center">
                              {tone === "running" ? (
                                <span className="text-[10px] bg-amber-500/20 text-amber-500 px-1.5 py-0.5 rounded-full border border-amber-500/30">
                                  执行中
                                </span>
                              ) : (
                                <span className={["text-[10px] truncate", tone === "idle" ? "text-zinc-500" : "ui-text-muted"].join(" ")}>
                                  {tone === "completed" ? "已完成" : m.currentStepLabel || (m.totalCount ? "进行中" : "待开始")}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Hover card (only on hover/focus) */}
                      <div
                        className={[
                          "pointer-events-none absolute left-1/2 -translate-x-1/2 top-full mt-3",
                          "z-50",
                          "opacity-0 -translate-y-2 scale-[0.99]",
                          "transition-all duration-200 ease-out",
                          "group-hover:opacity-100 group-hover:translate-y-0 group-hover:scale-100",
                          "group-focus-visible:opacity-100 group-focus-visible:translate-y-0 group-focus-visible:scale-100",
                        ].join(" ")}
                        aria-hidden="true"
                      >
                        <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 rotate-45 border-l border-t border-[var(--border-subtle)] bg-[var(--surface-1)]" aria-hidden="true" />
                        <div className="relative w-[13.5rem] rounded-xl border border-white/10 bg-zinc-900 shadow-xl shadow-black/60 px-3 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-[11px] font-semibold ui-text-primary truncate">{label}</div>
                              <div className="mt-0.5 text-[10px] ui-text-muted truncate">
                                {m.currentStepLabel || (m.totalCount ? "进行中" : "待开始")}
                              </div>
                            </div>
                            <div className="shrink-0 text-[10px] tabular-nums ui-text-muted">
                              {pct}%
                            </div>
                          </div>
                          <div className="relative mt-2 h-1.5 rounded-full overflow-hidden bg-[var(--surface-3)]">
                            <div
                              className="h-full rounded-full transition-[width] duration-1000 ease-out relative overflow-hidden"
                              style={{
                                width: `${pct}%`,
                                background:
                                  tone === "completed" ? "#10b981" : tone === "running" ? "#f59e0b" : "#3f3f46",
                              }}
                            >
                              {tone === "running" ? (
                                <>
                                  <span
                                    className="absolute inset-0 opacity-40"
                                    style={{
                                      backgroundImage:
                                        "repeating-linear-gradient(45deg,rgba(255,255,255,0.22) 0,rgba(255,255,255,0.22) 6px,transparent 6px,transparent 12px)",
                                      backgroundSize: "16px 16px",
                                    }}
                                    aria-hidden="true"
                                  />
                                  <span
                                    className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent"
                                    style={{ transform: "translateX(-120%)", animation: "module-stepper-shimmer 1.6s ease-in-out infinite" }}
                                    aria-hidden="true"
                                  />
                                </>
                              ) : null}
                            </div>
                          </div>
                          <div className="mt-1 flex items-center justify-between gap-2 text-[10px] ui-text-muted tabular-nums">
                            <span className="truncate">
                              {m.totalCount > 0 ? `${m.doneCount}/${m.totalCount}` : m.isPlaceholder ? "规划中" : "0/0"}
                            </span>
                            <span className="shrink-0">
                              {tone === "completed" ? "已完成" : tone === "running" ? "执行中" : "未开始"}
                            </span>
                          </div>
                        </div>
                      </div>
                    </button>
                  </li>
              );
            })}
            </ol>
        </div>
      </div>
    </section>
  );
}

