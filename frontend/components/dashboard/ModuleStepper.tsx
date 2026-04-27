"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ProjectOverviewModuleView } from "@/lib/projectOverviewStore";
import { Check, ChevronDown, Pin } from "lucide-react";
import { createPortal } from "react-dom";

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
    text: "ui-text-secondary",
    chip: "bg-emerald-500/20 text-emerald-500 border-emerald-500/30",
  },
  running: {
    dot: "bg-amber-500",
    ring: "ring-amber-500/25",
    rail: "bg-amber-500/40",
    text: "text-[var(--text-primary)] font-semibold",
    chip: "bg-amber-500/20 text-amber-500 border-amber-500/30",
  },
  idle: {
    dot: "bg-transparent border-2 border-[color-mix(in_srgb,var(--text-secondary)_50%,var(--border-strong))]",
    ring: "ring-[var(--border-subtle)]",
    rail: "bg-[color-mix(in_srgb,var(--text-secondary)_25%,var(--border-subtle))]",
    text: "ui-text-secondary",
    chip:
      "bg-[color-mix(in_oklab,var(--text-primary)_8%,transparent)] border-[var(--border-subtle)] text-[var(--text-secondary)]",
  },
} as const satisfies Record<StepTone, Record<string, string>>;

type StepperHoverState = {
  moduleId: string;
  label: string;
  tone: StepTone;
  pct: number;
  steps: ProjectOverviewModuleView["steps"];
  currentStepLabel: string | null;
  totalCount: number;
  doneCount: number;
  isPlaceholder: boolean | undefined;
};

function ModuleStepperHoverTooltip({
  hover,
  anchorRect,
  onTooltipPointerEnter,
  onTooltipPointerLeave,
}: {
  hover: StepperHoverState;
  anchorRect: DOMRect;
  onTooltipPointerEnter: () => void;
  onTooltipPointerLeave: () => void;
}) {
  const top = Math.round(anchorRect.bottom + 12);
  const left = Math.round(anchorRect.left + anchorRect.width / 2);
  const tone = hover.tone;
  const pct = hover.pct;
  const label = hover.label;

  return (
    <div
      className="fixed z-[20000] pointer-events-none"
      style={{ top, left, transform: "translateX(-50%)" }}
      aria-hidden="true"
    >
      <div
        className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 rotate-45 border-l border-t border-[var(--border-subtle)] bg-[var(--surface-elevated)]"
        aria-hidden="true"
      />
      <div
        onMouseEnter={onTooltipPointerEnter}
        onMouseLeave={onTooltipPointerLeave}
        className="relative pointer-events-auto w-[17.25rem] max-w-[min(100vw-2rem,21rem)] rounded-xl border border-[var(--border-subtle)] px-3.5 py-2.5 ui-elevation-4"
      >
        <div className="flex items-baseline justify-between gap-2 border-b border-[var(--border-subtle)]/80 pb-2.5">
          <div className="min-w-0">
            <div className="text-xs font-semibold leading-tight tracking-tight text-[var(--text-primary)] truncate">
              {label}
            </div>
            <div className="mt-1 text-[10px] leading-relaxed text-[var(--text-secondary)] truncate">
              {hover.currentStepLabel || (hover.totalCount ? "进行中" : "待开始")}
            </div>
          </div>
          <div className="shrink-0 text-[10px] font-medium tabular-nums text-[var(--text-secondary)]">{pct}%</div>
        </div>

        {hover.steps && hover.steps.length > 0 ? (
          <ul className="mt-2.5 max-h-44 space-y-2 overflow-y-auto pr-0.5 text-left [scrollbar-gutter:stable]">
            {hover.steps.map((s) => (
              <li key={s.id} className="flex items-start gap-2 text-[10px] leading-snug w-full">
                {s.done ? (
                  <Check className="mt-0.5 h-3 w-3 shrink-0 text-emerald-400" strokeWidth={2.5} aria-hidden />
                ) : (
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full border border-[var(--border-strong)] bg-transparent" aria-hidden />
                )}
                <span className={["min-w-0 flex-1", s.done ? "text-[var(--text-primary)]/90" : "ui-text-muted"].join(" ")}>{s.name}</span>
                <span
                  className={[
                    "shrink-0 text-[9px] tabular-nums",
                    s.done ? "text-emerald-400/90" : "ui-text-muted",
                  ].join(" ")}
                >
                  {s.done ? "已完成" : "未完成"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2.5 text-[10px] leading-relaxed text-[var(--text-secondary)]">
            {hover.totalCount > 0
              ? "子任务与进度源同步中，请稍后重试"
              : "本阶段暂无可列出的子任务，仍显示总体完成度与阶段状态"}
          </p>
        )}

        <div className="relative mt-2.5 h-1.5 rounded-full overflow-hidden bg-[var(--surface-3)]">
          <div
            className="h-full rounded-full transition-[width] duration-1000 ease-out relative overflow-hidden"
            style={{
              width: `${pct}%`,
              background: tone === "completed" ? "#10b981" : tone === "running" ? "#f59e0b" : "#3f3f46",
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
            {hover.totalCount > 0
              ? `${hover.doneCount}/${hover.totalCount}`
              : hover.isPlaceholder
                ? "规划中"
                : "0/0"}
          </span>
          <span className="shrink-0">
            {tone === "completed" ? "已完成" : tone === "running" ? "执行中" : "未开始"}
          </span>
        </div>
      </div>
    </div>
  );
}

const HOVER_CLOSE_MS = 240;

export function ModuleStepper({
  modules,
  activeModuleId = null,
  onSelectModule,
  className,
}: Props) {
  const clickable = Boolean(onSelectModule);
  const [hover, setHover] = useState<StepperHoverState | null>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const anchorElRef = useRef<HTMLElement | null>(null);
  const hoverLeaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** 避免在 SSR/首帧对 document.body 做 Portal，降低 React 19 下 removeChild 竞态 */
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const clearHoverCloseTimer = useCallback(() => {
    if (hoverLeaveTimerRef.current) {
      clearTimeout(hoverLeaveTimerRef.current);
      hoverLeaveTimerRef.current = null;
    }
  }, []);

  const clearHover = useCallback(() => {
    anchorElRef.current = null;
    setAnchorRect(null);
    setHover(null);
  }, []);

  const scheduleHideHover = useCallback(() => {
    clearHoverCloseTimer();
    hoverLeaveTimerRef.current = setTimeout(() => {
      hoverLeaveTimerRef.current = null;
      clearHover();
    }, HOVER_CLOSE_MS);
  }, [clearHover, clearHoverCloseTimer]);

  useEffect(() => () => clearHoverCloseTimer(), [clearHoverCloseTimer]);

  const hoverOpen = Boolean(hover && anchorRect);

  /** anchor rect 跟随滚动 / resize 即时更新，浮层不会“贴错”位置 */
  useEffect(() => {
    if (!hoverOpen) return;
    const update = () => {
      const el = anchorElRef.current;
      if (!el) return;
      setAnchorRect(el.getBoundingClientRect());
    };
    update();
    const onScroll = () => update();
    const onResize = () => update();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
  }, [hoverOpen]);

  const openHoverFor = useCallback(
    (m: ProjectOverviewModuleView, anchor: HTMLElement) => {
      const label = cleanLabel(m.label, m.moduleId);
      const tone = toneOf(m, activeModuleId);
      const pct = pctOf(m);
      clearHoverCloseTimer();
      anchorElRef.current = anchor;
      setAnchorRect(anchor.getBoundingClientRect());
      setHover({
        moduleId: m.moduleId,
        label,
        tone,
        pct,
        steps: m.steps,
        currentStepLabel: m.currentStepLabel ?? null,
        totalCount: m.totalCount,
        doneCount: m.doneCount,
        isPlaceholder: m.isPlaceholder,
      });
    },
    [activeModuleId, clearHoverCloseTimer],
  );

  return (
    <section
      className={["px-2 w-full min-w-0 max-w-full", className].filter(Boolean).join(" ")}
    >
      <div className="w-full min-w-0 max-w-full rounded-2xl ui-elevation-1 overflow-visible">
        <div className="relative px-3 py-3 min-w-0">
            <ol className="flex items-start w-full" role="list" aria-label="阶段进展">
            {modules.map((m, idx) => {
              const tone = toneOf(m, activeModuleId);
              /**
               * 仅占位 = 无 module.json 等注册信息，禁止切换大盘；**仍**展示 task 进展浮层，避免「只有已装模块能悬停」
               * @see buildOverviewViewsFromTaskStatus: isPlaceholder: !reg
               */
              const isPlaceholder = Boolean(m.isPlaceholder);
              const isActive = (activeModuleId ?? "") && m.moduleId === activeModuleId;
              const label = cleanLabel(m.label, m.moduleId);

              return (
                <li
                  key={m.taskModuleId || m.moduleId}
                  className="relative flex-1 min-w-0"
                  role="listitem"
                  onPointerEnter={(e) => {
                    /** 跨格切换：mouseleave 旧格 + mouseenter 新格几乎同帧到达，先取消上一格的关闭计时再开新的 */
                    const li = e.currentTarget;
                    const anchor = li.querySelector<HTMLElement>("[data-stepper-anchor]");
                    if (!anchor) return;
                    openHoverFor(m, anchor);
                  }}
                  onPointerLeave={() => {
                    scheduleHideHover();
                  }}
                >
                  {/* 贯穿连线：从当前圆心向右发射，连接到下一个圆心；pointer-events-none 不阻塞列命中 */}
                  {idx < modules.length - 1 ? (
                    <div
                      className={[
                        "pointer-events-none absolute top-[22px] left-1/2 w-full h-[2px] overflow-hidden",
                        tone === "completed" ? TONE.completed.rail : tone === "running" ? TONE.running.rail : TONE.idle.rail,
                      ].join(" ")}
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
                      aria-disabled={isPlaceholder}
                      onClick={() => {
                        if (isPlaceholder || !clickable) return;
                        onSelectModule?.(m.moduleId);
                      }}
                      onFocus={(e) => {
                        const anchor = e.currentTarget.querySelector<HTMLElement>("[data-stepper-anchor]");
                        if (anchor) openHoverFor(m, anchor);
                      }}
                      onBlur={() => scheduleHideHover()}
                      className={[
                        "ui-motion group group/step relative z-10 flex w-full min-w-0 min-h-[4.5rem] justify-center border-0 bg-transparent p-0 text-inherit",
                        isPlaceholder ? "cursor-help opacity-70" : "cursor-default",
                        "focus:outline-none focus-visible:ring-0",
                      ].join(" ")}
                      aria-label={label}
                    >
                      <div
                        className="group/row flex min-h-[4.5rem] w-full min-w-0 flex-col items-center py-0.5"
                      >
                        <div
                          className={[
                            "relative mx-auto flex w-fit max-w-full min-w-0 flex-col items-center gap-1.5 rounded-xl px-2.5 py-1.5",
                            "group-hover/row:bg-[var(--surface-2)]/55",
                            isActive
                              ? "ring-1 ring-[color-mix(in_oklab,var(--accent)_32%,transparent)]"
                              : "group-focus-within:ring-1 group-focus-within:ring-[color-mix(in_oklab,var(--accent)_32%,transparent)]",
                            "ui-motion",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          data-stepper-anchor
                        >
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
                                TONE.idle.dot,
                                TONE.idle.ring,
                                "group-hover/step:border-[color-mix(in_srgb,var(--text-primary)_35%,var(--text-secondary))] group-hover/step:shadow-sm",
                              ].join(" ")}
                              aria-hidden="true"
                              title="未开始"
                            />
                          )}
                        </span>

                        <div className="w-full min-w-0 text-center">
                          <div className="w-full min-w-0">
                            <div className={["text-xs font-semibold truncate text-center", tone === "idle" ? "text-[var(--text-primary)]" : TONE[tone].text].join(" ")}>
                              {label}
                            </div>
                            <div className="mt-1 flex justify-center">
                              {tone === "running" ? (
                                <span className="text-[10px] bg-amber-500/20 text-amber-500 px-1.5 py-0.5 rounded-full border border-amber-500/30">
                                  执行中
                                </span>
                              ) : (
                                <span className={["text-[10px] truncate", tone === "idle" ? "text-[var(--text-secondary)]" : "ui-text-muted"].join(" ")}>
                                  {tone === "completed" ? "已完成" : m.currentStepLabel || (m.totalCount ? "进行中" : "待开始")}
                                </span>
                              )}
                            </div>
                          </div>
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
      {mounted && hover && anchorRect
        ? createPortal(
            <ModuleStepperHoverTooltip
              hover={hover}
              anchorRect={anchorRect}
              onTooltipPointerEnter={clearHoverCloseTimer}
              onTooltipPointerLeave={scheduleHideHover}
            />,
            document.body,
          )
        : null}
    </section>
  );
}

/* ── ModuleStepperCompact ─────────────────────────────────────
 * 单行胶囊：默认收起，仅展示「当前阶段 · 状态」与「{done}/{total}」。
 * 点击展开 popover，复用完整 <ModuleStepper /> 视图；ESC 或点外部关闭。
 * 用于聊天区顶部右侧，替代原全宽 80px 进度条。
 * ────────────────────────────────────────────────────────── */
type CompactProps = {
  modules: ProjectOverviewModuleView[];
  activeModuleId?: string | null;
  className?: string;
  /** 提供后，Popover 标题栏显示「固定到顶栏」图钉，与设置中心里的「顶栏常驻」为同一状态 */
  onDock?: () => void;
};

export function ModuleStepperCompact({ modules, activeModuleId = null, className, onDock }: CompactProps) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  const total = modules.length;
  const completed = modules.filter((m) => m.status === "completed").length;
  const running = modules.find((m) => m.status === "running");
  const focusedModule =
    running ?? (activeModuleId ? modules.find((m) => m.moduleId === activeModuleId) : undefined) ?? modules.find((m) => m.status !== "completed");
  const tone: StepTone = running
    ? "running"
    : completed === total && total > 0
      ? "completed"
      : "idle";
  const dotClass =
    tone === "running"
      ? "bg-amber-500"
      : tone === "completed"
        ? "bg-emerald-500"
        : "bg-[var(--border-strong)]";
  const statusText = tone === "running" ? "执行中" : tone === "completed" ? "已完成" : "待开始";
  const currentLabel = focusedModule
    ? cleanLabel(focusedModule.label, focusedModule.moduleId)
    : total
      ? "全部完成"
      : "—";

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node | null;
      if (!t) return;
      if (triggerRef.current?.contains(t)) return;
      if (popoverRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const update = () => {
      const el = triggerRef.current;
      if (el) setAnchorRect(el.getBoundingClientRect());
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open]);

  const popoverWidth = typeof window !== "undefined" ? Math.min(window.innerWidth - 16, 560) : 560;
  const popoverLeft = anchorRect
    ? Math.max(8, Math.round(anchorRect.right - popoverWidth))
    : 8;
  const popoverTop = anchorRect ? Math.round(anchorRect.bottom + 8) : 0;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`流程进度 ${completed} 于 ${total}，当前 ${currentLabel} ${statusText}`}
        className={[
          "ui-elevation-1 ui-motion ui-hover-soft inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} aria-hidden />
        <span className="ui-text-secondary truncate max-w-[12rem]">
          {currentLabel} · {statusText}
        </span>
        <span className="ui-text-muted tabular-nums">{completed}/{total}</span>
        <ChevronDown
          size={14}
          className="ui-motion-fast ui-text-muted"
          style={{ transform: open ? "rotate(180deg)" : "rotate(0deg)" }}
          aria-hidden
        />
      </button>
      {mounted && open && anchorRect
        ? createPortal(
            <div
              ref={popoverRef}
              role="dialog"
              aria-label="完整流程"
              className="fixed z-[9999] ui-elevation-4 rounded-xl p-3"
              style={{
                top: popoverTop,
                left: popoverLeft,
                width: popoverWidth,
                maxWidth: "calc(100vw - 1rem)",
              }}
            >
              {onDock ? (
                <div className="mb-3 flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2.5">
                  <span className="text-xs font-semibold ui-text-primary">流程进度</span>
                  <button
                    type="button"
                    onClick={() => {
                      onDock();
                      setOpen(false);
                    }}
                    className="nav-icon-btn p-1.5"
                    title="固定到顶栏"
                    aria-label="固定到顶栏"
                  >
                    <Pin size={16} strokeWidth={2.25} aria-hidden />
                  </button>
                </div>
              ) : null}
              <ModuleStepper modules={modules} activeModuleId={activeModuleId} />
            </div>,
            document.body,
          )
        : null}
    </>
  );
}

