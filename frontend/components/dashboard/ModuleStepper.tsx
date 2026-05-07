"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ProjectOverviewModuleView } from "@/lib/projectOverviewStore";
import { canonicalModuleIdForMerge } from "@/lib/moduleDisplayLabels";
import { Check, ChevronDown, Pin } from "lucide-react";
import { createPortal } from "react-dom";

type StepTone = "completed" | "running" | "idle";

type Props = {
  modules: ProjectOverviewModuleView[];
  activeModuleId?: string | null;
  onSelectModule?: (id: string) => void;
  className?: string;
};

function railClassForPair(from: StepTone, to: StepTone): string {
  // 只控制“呈现语义”，不参与任何进度推进逻辑。
  if (from === "completed" && to === "completed") return "bg-emerald-500/50";
  if (from === "completed" && to === "running") {
    return "bg-gradient-to-r from-emerald-500/55 via-[color-mix(in_oklab,var(--success)_45%,var(--accent))] to-[color-mix(in_oklab,var(--accent)_70%,transparent)]";
  }
  if (from === "running" && to === "idle") {
    return "bg-gradient-to-r from-[color-mix(in_oklab,var(--accent)_70%,transparent)] to-[var(--border-subtle)]";
  }
  if (from === "running" && to === "running") {
    return "bg-[color-mix(in_oklab,var(--accent)_42%,var(--border-subtle))]";
  }
  if (from === "idle" && to === "idle") return "bg-[var(--border-subtle)]";
  // 其它边界组合：保持语义化但不抢戏
  if (from === "running" && to === "completed") {
    return "bg-gradient-to-r from-[color-mix(in_oklab,var(--accent)_70%,transparent)] to-emerald-500/45";
  }
  if (from === "idle" && to === "running") {
    return "bg-gradient-to-r from-[var(--border-subtle)] to-[color-mix(in_oklab,var(--accent)_70%,transparent)]";
  }
  if (from === "idle" && to === "completed") {
    return "bg-gradient-to-r from-[var(--border-subtle)] to-emerald-500/45";
  }
  return "bg-[var(--border-subtle)]";
}

function toneOf(m: ProjectOverviewModuleView): StepTone {
  /**
   * 仅影响“呈现语义”，不影响任何后端/推进逻辑：
   * - tone 只认“客观进度”（status / pct / counts / label），不再被 activeModuleId 劫持。
   * - 兜底：在 API/registry 合并不稳定时，仍能按“已完成”信号渲染为 completed。
   */
  const pct = pctOf(m);
  const stepLabel = String(m.currentStepLabel ?? "").trim();
  const doneByCounts = m.totalCount > 0 && m.doneCount >= m.totalCount;
  const completedBySignal = m.status === "completed" || pct >= 100 || doneByCounts || stepLabel === "已完成";
  if (completedBySignal) return "completed";
  if (m.status === "running") return "running";
  return "idle";
}

function visualToneOf(m: ProjectOverviewModuleView, tone: StepTone): StepTone {
  // 仅展示层：把 completed/running 统一为同等“亮度”，不改变真实 status。
  if (m.uiEmphasis === "active") return "running";
  return tone;
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
    // 统一 completed/running 的“亮度”来源：用同一套柔光阴影强度，避免某一态显得更亮
    dot: "bg-emerald-500 shadow-[0_0_18px_-6px_rgba(255,255,255,0.26)]",
    ring: "ring-0",
    /** 克制的连线：完成段也只有 1.5px，不抢戏 */
    rail: "bg-emerald-500/50",
    /**
     * 完成态也需要“亮”，但仍低于 running 的视觉优先级：
     * - 主标题用 primary（不再 muted）
     * - 轻微降低饱和度与字重，保持 running 更醒目
     */
    text: "text-[var(--text-primary)]/85 font-semibold tracking-tight",
    chip: "bg-emerald-500/12 text-emerald-500/85 border border-transparent text-[11px]",
  },
  running: {
    dot: "bg-[var(--accent)] shadow-[0_0_18px_-6px_rgba(255,255,255,0.26)]",
    ring: "ring-0",
    /** 当前段的连线：accent → border-subtle 渐变，预示未完成 */
    rail: "bg-gradient-to-r from-[color-mix(in_oklab,var(--accent)_70%,transparent)] to-[var(--border-subtle)]",
    text: "text-[var(--text-primary)] font-semibold tracking-tight",
    chip: "bg-[var(--accent-bg-soft)] text-[var(--accent)] border-[var(--accent-border)]",
  },
  idle: {
    dot: "bg-[var(--surface-3)] border border-[var(--border-strong)]",
    ring: "ring-0",
    rail: "bg-[var(--border-subtle)]",
    text: "ui-text-secondary",
    chip: "bg-transparent border-[var(--border-subtle)] text-[var(--text-secondary)]",
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
            <div className="mt-1 ui-text-eyebrow leading-relaxed text-[var(--text-secondary)] truncate">
              {hover.currentStepLabel || (hover.totalCount ? "进行中" : "待开始")}
            </div>
          </div>
          <div className="shrink-0 ui-text-eyebrow font-medium tabular-nums text-[var(--text-secondary)]">{pct}%</div>
        </div>

        {hover.steps && hover.steps.length > 0 ? (
          <ul className="mt-2.5 max-h-44 space-y-2 overflow-y-auto pr-0.5 text-left [scrollbar-gutter:stable]">
            {hover.steps.map((s) => (
              <li key={s.id} className="flex items-start gap-2 ui-text-eyebrow leading-snug w-full">
                {s.done ? (
                  <Check className="mt-0.5 h-3 w-3 shrink-0 ui-status-success" strokeWidth={2.5} aria-hidden />
                ) : (
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full border border-[var(--border-strong)] bg-transparent" aria-hidden />
                )}
                <span className={["min-w-0 flex-1", s.done ? "text-[var(--text-primary)]/90" : "ui-text-muted"].join(" ")}>{s.name}</span>
                <span
                  className={[
                    "shrink-0 ui-text-eyebrow tabular-nums",
                    s.done ? "ui-status-success" : "ui-text-muted",
                  ].join(" ")}
                >
                  {s.done ? "已完成" : "未完成"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2.5 ui-text-eyebrow leading-relaxed text-[var(--text-secondary)]">
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
              background:
                tone === "completed"
                  ? "var(--success)"
                  : tone === "running"
                    ? "var(--accent)"
                    : "color-mix(in oklab, var(--border-strong) 65%, transparent)",
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
        <div className="mt-1 flex items-center justify-between gap-2 ui-text-eyebrow ui-text-muted tabular-nums">
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

export function ModuleStepper(props: Props) {
  const { modules, onSelectModule, className } = props;
  const clickable = Boolean(onSelectModule);
  const [hover, setHover] = useState<StepperHoverState | null>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const anchorElRef = useRef<HTMLElement | null>(null);
  const hoverLeaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isHoveringTooltipRef = useRef(false);
  const rafIdRef = useRef<number | null>(null);
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
    if (isHoveringTooltipRef.current) return;
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
    const schedule = () => {
      if (rafIdRef.current != null) return;
      rafIdRef.current = window.requestAnimationFrame(() => {
        rafIdRef.current = null;
        update();
      });
    };
    const onScroll = () => schedule();
    const onResize = () => schedule();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
      if (rafIdRef.current != null) {
        window.cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [hoverOpen]);

  const openHoverFor = useCallback(
    (m: ProjectOverviewModuleView, anchor: HTMLElement) => {
      const label = cleanLabel(m.label, m.moduleId);
      const tone = toneOf(m);
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
    [clearHoverCloseTimer],
  );

  return (
    <section
      className={["px-2 w-full min-w-0 max-w-full", className].filter(Boolean).join(" ")}
    >
      <div className="w-full min-w-0 max-w-full rounded-2xl ui-elevation-1 overflow-visible">
        <div className="relative px-3 py-3 min-w-0">
            <ol className="flex items-start w-full" role="list" aria-label="阶段进展">
            {modules.map((m, idx) => {
              const tone = toneOf(m);
              const visualTone = visualToneOf(m, tone);
              /**
               * 仅占位 = 无 module.json 等注册信息，禁止切换大盘；**仍**展示 task 进展浮层，避免「只有已装模块能悬停」
               * @see buildOverviewViewsFromTaskStatus: isPlaceholder: !reg
               */
              const isPlaceholder = Boolean(m.isPlaceholder);
              const label = cleanLabel(m.label, m.moduleId);

              return (
                <li
                  key={m.taskModuleId || m.moduleId}
                  className="relative flex-1 min-w-0"
                  role="listitem"
                  /**
                   * 仅诊断用 data-* 属性（不参与样式/逻辑）：
                   * 用来在 DevTools 直接看每一项的 tone / visualTone / uiEmphasis / status，
                   * 以验证“为何两项 completed 视觉不一致”的归属（CSS or 数据）。
                   */
                  data-debug-module-id={m.moduleId}
                  data-debug-task-module-id={m.taskModuleId || ""}
                  data-debug-status={m.status}
                  data-debug-emphasis={m.uiEmphasis ?? "(unset)"}
                  data-debug-tone={tone}
                  data-debug-visual-tone={visualTone}
                  data-debug-done={`${m.doneCount}/${m.totalCount}`}
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
                  {/* 贯穿连线：克制的 1.5px hairline，对齐圆心（li padding 8px + outer h-8 半径 16px = 24px） */}
                  {idx < modules.length - 1 ? (
                    <div
                      className={[
                        "pointer-events-none absolute top-[24px] overflow-hidden rounded-full",
                        visualTone === "running" ? "h-[2px]" : "h-[1.5px]",
                        railClassForPair(visualTone, visualToneOf(modules[idx + 1], toneOf(modules[idx + 1]))),
                      ].join(" ")}
                      style={{
                        zIndex: 0,
                        transition: "background-color 240ms ease",
                        // 让连线段只出现在两个圆圈之间：两端各留出圆圈半径（16px）的“安全区”
                        left: "calc(50% + 16px)",
                        width: "calc(100% - 32px)",
                      }}
                      aria-hidden="true"
                    />
                  ) : null}
                    <button
                      type="button"
                      aria-disabled={isPlaceholder}
                      tabIndex={isPlaceholder ? -1 : 0}
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
                        /**
                         * 局部覆盖 globals.css 里 `:is(:disabled, [aria-disabled="true"]) { opacity: 0.45 }`：
                         * Stepper 项作为“信息步骤”即使无法点击也应保持原亮度，避免 placeholder 模块（如智慧工勘）
                         * 被整体压暗 45% 与“作业管理/建模仿真”形成不一致的视觉层级。
                         */
                        "aria-disabled:opacity-100",
                        isPlaceholder ? "cursor-help" : "cursor-default",
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
                            "ui-motion",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          data-stepper-anchor
                        >
                        <span className="relative inline-flex h-8 w-8 items-center justify-center">
                          {/* mask background so connector never shows through the circle */}
                          <span
                            className="pointer-events-none absolute z-10"
                            style={{
                              // 先切断“连线贴圆”的感觉：在圆心高度做一条横向 cutout（留 1~2px 间隔）
                              top: "50%",
                              left: "50%",
                              transform: "translate(-50%, -50%)",
                              height: 10,
                              width: 56,
                              borderRadius: 999,
                              background:
                                "linear-gradient(90deg, transparent 0%, var(--paper-card) 18%, var(--paper-card) 82%, transparent 100%)",
                            }}
                            aria-hidden="true"
                          />
                          <span
                            className="pointer-events-none absolute rounded-full z-10"
                            style={{
                              // 上大下小：隔离 rail 叠色与光晕，同时避免下沿压住阶段文字
                              top: -10,
                              left: -10,
                              right: -10,
                              bottom: -6,
                              background:
                                "radial-gradient(circle, var(--paper-card) 0%, var(--paper-card) 66%, transparent 82%)",
                            }}
                            aria-hidden="true"
                          />
                          {tone === "completed" ? (
                            <span
                              className={[
                                "relative z-20 inline-flex h-7 w-7 items-center justify-center rounded-full",
                                TONE.completed.ring,
                                TONE.completed.dot,
                              ].join(" ")}
                              aria-hidden="true"
                            >
                              <Check size={16} strokeWidth={3} className="text-white" />
                            </span>
                          ) : tone === "running" ? (
                            <span
                              className={[
                                /**
                                 * 运行态：保持“黄/Accent”语义，但把亮度来源从“小点”升级为
                                 * “同尺寸圆底 + 同强度柔光”，以对齐 completed 的视觉存在感。
                                 */
                                "relative z-20 inline-flex h-7 w-7 items-center justify-center rounded-full",
                                "bg-[color-mix(in_oklab,var(--accent)_22%,var(--surface-1))]",
                                "ring-1 ring-[color-mix(in_oklab,var(--accent)_35%,transparent)]",
                                "shadow-[0_0_18px_-6px_rgba(255,255,255,0.26)]",
                                TONE.running.ring,
                              ].join(" ")}
                              aria-hidden="true"
                            >
                              <span
                                className={[
                                  // 仍保留黄点语义，但用白色高光确保与完成态对比一致
                                  "relative inline-flex h-2.5 w-2.5 rounded-full",
                                  "bg-[var(--accent)]",
                                  "shadow-[0_0_10px_-6px_rgba(255,255,255,0.55)]",
                                ].join(" ")}
                                aria-hidden
                              />
                            </span>
                          ) : (
                            <span
                              className={[
                                /* idle：与 completed/running 同尺寸 24px，hairline 双层环
                                 * 这样三态在视觉重量上完全对齐，连接线不会"跳格"
                                 */
                                "relative z-20 inline-flex h-7 w-7 items-center justify-center rounded-full bg-[var(--surface-1)]",
                                "border-2 border-[var(--border-subtle)]",
                                "group-hover/step:border-[var(--border-strong)]",
                                "ui-motion-fast",
                                TONE.idle.ring,
                              ].join(" ")}
                              aria-hidden="true"
                              title="未开始"
                            >
                              {/* 内嵌一个小 idle 点，避免空环看起来"挂着" */}
                              <span
                                aria-hidden
                                className={["h-2 w-2 rounded-full", TONE.idle.dot].join(" ")}
                              />
                            </span>
                          )}
                        </span>

                        <div className="w-full min-w-0 text-center">
                          <div className="w-full min-w-0">
                            <div
                              className={[
                                "text-[14px] font-semibold leading-tight truncate text-center",
                                tone === "idle" ? "ui-text-secondary opacity-60" : TONE[visualTone].text,
                              ].join(" ")}
                            >
                              {label}
                            </div>
                            <div className="mt-1.5 flex justify-center">
                              {tone === "running" ? (
                                <span className={["ui-text-eyebrow px-2 py-0.5 rounded-full border", TONE.running.chip].join(" ")}>
                                  执行中
                                </span>
                              ) : (
                                <span
                                  className={[
                                    "text-[11.5px] truncate",
                                    tone === "idle"
                                      ? "text-[var(--text-secondary)]"
                                      : tone === "completed"
                                        ? "text-[var(--text-primary)]/65"
                                        : "ui-text-muted",
                                  ].join(" ")}
                                >
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
              onTooltipPointerEnter={() => {
                isHoveringTooltipRef.current = true;
                clearHoverCloseTimer();
              }}
              onTooltipPointerLeave={() => {
                isHoveringTooltipRef.current = false;
                scheduleHideHover();
              }}
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
  const completed = modules.filter((m) => toneOf(m) === "completed").length;
  const running = modules.find((m) => toneOf(m) === "running");
  const focusedModule =
    running ??
      (activeModuleId
        ? modules.find(
            (m) => canonicalModuleIdForMerge(m.moduleId) === canonicalModuleIdForMerge(activeModuleId ?? ""),
          )
        : undefined) ??
      modules.find((m) => toneOf(m) !== "completed");
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

