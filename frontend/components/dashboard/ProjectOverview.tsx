"use client";

import { useId, useMemo } from "react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ModuleEntry } from "@/components/DashboardNavigator";

type Props = {
  modules: ModuleEntry[];
  onSelectModule: (id: string) => void;
};

export function ProjectOverview({ modules, onSelectModule }: Props) {
  const runningCount = modules.filter((item) => item.status === "running").length;
  const completedCount = modules.filter((item) => item.status === "completed").length;
  const pendingCount = Math.max(0, modules.length - runningCount - completedCount);
  const completionPct = modules.length ? Math.round((completedCount / modules.length) * 100) : 0;

  // 任务活跃态的语义化趋势（在没有真实历史时仍能拉出视觉重量）
  const activity = deriveActivity(runningCount, modules.length);

  return (
    <div className="relative h-full min-h-0">
      <div
        className="absolute inset-0 overflow-y-auto flex flex-col"
        style={{ padding: "var(--panel-pad)", gap: "var(--section-gap)" }}
      >
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold ui-text-primary tracking-tight">项目总览</h2>
          <span className="text-[12.5px] ui-text-muted tabular-nums">
            {runningCount}/{modules.length} 模块活跃
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <ProgressCard
            eyebrow="项目完成度"
            pct={completionPct}
            completedCount={completedCount}
            total={modules.length}
          />
          <ActivityCard
            eyebrow="任务活跃态"
            runningCount={runningCount}
            pendingCount={pendingCount}
            activity={activity}
          />
        </div>

        {modules.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center py-16">
            <div className="ui-text-eyebrow ui-text-muted opacity-70">PLAN</div>
            <p className="text-sm ui-text-muted leading-relaxed">
              等待 Skill 执行…
              <br />
              <span className="ui-text-label opacity-60">Skill 启动后，模块大盘将自动出现</span>
            </p>
          </div>
        ) : (
          <ActivityTimeline modules={modules} onSelectModule={onSelectModule} />
        )}
      </div>

      {/* 顶/底各一道 14px 渐变，提示“还有内容”，不遮挡 sticky 段头（段头 z-2，这里 z-1） */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-3.5 z-[1]"
        style={{ background: "linear-gradient(to bottom, var(--paper-card) 0%, transparent 100%)" }}
      />
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-3.5 z-[1]"
        style={{ background: "linear-gradient(to top, var(--paper-card) 0%, transparent 100%)" }}
      />
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   ProgressCard —— 环形进度（Linear 骨架），主数字字阶领先副 caption 三档
   ───────────────────────────────────────────────────────────── */
function ProgressCard({
  eyebrow,
  pct,
  completedCount,
  total,
}: {
  eyebrow: string;
  pct: number;
  completedCount: number;
  total: number;
}) {
  return (
    <div
      className="ui-elevation-2 group relative overflow-hidden rounded-2xl border border-[var(--border-subtle)]"
      style={{ padding: "var(--card-pad)" }}
    >
      {/* 卡内极淡 accent 径向晕：避免"灰盒子"感，又不抢眼 */}
      <span
        aria-hidden
        className="pointer-events-none absolute -top-12 -right-12 h-32 w-32 rounded-full"
        style={{
          background:
            "radial-gradient(circle, color-mix(in oklab, var(--accent) 14%, transparent) 0%, transparent 70%)",
        }}
      />
      <div className="relative flex items-start justify-between gap-4">
        <div className="flex flex-col gap-2 min-w-0">
          <p className="text-[12px] font-semibold ui-text-secondary tracking-[0.06em] uppercase">{eyebrow}</p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-[2.75rem] font-semibold tracking-tight tabular-nums ui-text-primary leading-none">
              {pct}
            </span>
            <span className="text-lg font-medium ui-text-muted leading-none">%</span>
          </div>
          <p className="text-[12.5px] ui-text-muted">
            <span className="tabular-nums">{completedCount}</span>
            <span className="opacity-70"> / </span>
            <span className="tabular-nums">{total || 0}</span>
            <span className="ml-1">个模块完成</span>
          </p>
        </div>

        <ProgressRing pct={pct} size={72} stroke={6} />
      </div>
    </div>
  );
}

function ProgressRing({
  pct,
  size = 56,
  stroke = 4,
}: {
  pct: number;
  size?: number;
  stroke?: number;
}) {
  const gradId = useId();
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const safePct = Math.max(0, Math.min(100, pct));
  const offset = circumference * (1 - safePct / 100);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`完成度 ${safePct}%`}
      className="shrink-0"
    >
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.35" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="1" />
        </linearGradient>
      </defs>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--border-subtle)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{
          transition: "stroke-dashoffset var(--motion-slow) var(--ease-out)",
        }}
      />
    </svg>
  );
}

/* ─────────────────────────────────────────────────────────────
   ActivityCard —— 主数字 + 趋势箭头 + 状态徽章
   ───────────────────────────────────────────────────────────── */
type ActivityLevel = "high" | "mid" | "idle";

type ActivityMeta = {
  level: ActivityLevel;
  label: string;          // 状态徽章文案
  badgeColor: string;     // 徽章背景 token
  badgeFg: string;        // 徽章文字 token
  trend: "up" | "flat" | "down";
};

function deriveActivity(runningCount: number, total: number): ActivityMeta {
  if (total === 0 || runningCount === 0) {
    return {
      level: "idle",
      label: "空闲",
      badgeColor: "color-mix(in oklab, var(--text-muted) 18%, transparent)",
      badgeFg: "var(--text-muted)",
      trend: "down",
    };
  }
  if (runningCount >= 3 || runningCount / Math.max(1, total) >= 0.5) {
    return {
      level: "high",
      label: "高活跃",
      badgeColor: "var(--accent-bg-soft)",
      badgeFg: "var(--accent)",
      trend: "up",
    };
  }
  return {
    level: "mid",
    label: "推进中",
    badgeColor: "color-mix(in oklab, var(--success) 18%, transparent)",
    badgeFg: "var(--success)",
    trend: "flat",
  };
}

function ActivityCard({
  eyebrow,
  runningCount,
  pendingCount,
  activity,
}: {
  eyebrow: string;
  runningCount: number;
  pendingCount: number;
  activity: ActivityMeta;
}) {
  const TrendIcon = useMemo(
    () =>
      activity.trend === "up"
        ? ArrowUpRight
        : activity.trend === "down"
          ? ArrowDownRight
          : Minus,
    [activity.trend],
  );

  const trendColor =
    activity.trend === "up"
      ? "var(--accent)"
      : activity.trend === "down"
        ? "var(--text-muted)"
        : "var(--success)";

  return (
    <div
      className="ui-elevation-2 group relative overflow-hidden rounded-2xl border border-[var(--border-subtle)]"
      style={{ padding: "var(--card-pad)" }}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute -top-12 -right-12 h-32 w-32 rounded-full"
        style={{
          background:
            "radial-gradient(circle, color-mix(in oklab, " +
            (activity.level === "high"
              ? "var(--accent)"
              : activity.level === "mid"
                ? "var(--success)"
                : "var(--text-muted)") +
            " 14%, transparent) 0%, transparent 70%)",
        }}
      />
      <div className="relative flex items-start justify-between gap-3">
        <p className="text-[12px] font-semibold ui-text-secondary tracking-[0.06em] uppercase">{eyebrow}</p>
        <span
          className="text-[10.5px] font-bold inline-flex items-center gap-1 rounded-full px-2 py-0.5 tracking-[0.08em] uppercase"
          style={{
            background: activity.badgeColor,
            color: activity.badgeFg,
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: activity.badgeFg }}
            aria-hidden
          />
          {activity.label}
        </span>
      </div>

      <div className="relative mt-2 flex items-baseline gap-2">
        <span className="text-[2.75rem] font-semibold tracking-tight tabular-nums ui-text-primary leading-none">
          {runningCount}
        </span>
        <span
          className="inline-flex items-center gap-0.5 text-[13px] font-medium tabular-nums"
          style={{ color: trendColor }}
        >
          <TrendIcon size={15} strokeWidth={2.25} aria-hidden />
          <span>{activity.trend === "up" ? "活跃" : activity.trend === "down" ? "低位" : "持平"}</span>
        </span>
      </div>

      <p className="relative mt-2 text-[12.5px] ui-text-muted">
        <span className="tabular-nums">{runningCount}</span>
        <span className="ml-1">运行中 ·</span>
        <span className="ml-1 tabular-nums">{pendingCount}</span>
        <span className="ml-1">待开始</span>
      </p>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   ActivityTimeline —— Linear / Vercel 风格的事件流
   · 极细 border-subtle 竖线串联节点
   · 等宽计数（tabular-nums + font-mono）替代时间戳，呈现"日志感"
   · 节点 8px：completed = emerald 实心；running = accent 实心 + 双层 ping；idle = hairline 空心
   · 完成模块名 muted；当前模块名 primary + 加粗；未开始模块名 muted 50%
   · 点击 running/completed/idle 模块（非 placeholder）= 切到对应大盘
   ───────────────────────────────────────────────────────────── */
type TimelineModule = ModuleEntry;

function ActivityTimeline({
  modules,
  onSelectModule,
}: {
  modules: TimelineModule[];
  onSelectModule: (id: string) => void;
}) {
  const completed = modules.filter((m) => m.status === "completed").length;
  const completionRatio = modules.length > 0 ? completed / modules.length : 0;

  return (
    <section
      className="ui-elevation-2 rounded-2xl border border-[var(--border-subtle)] flex flex-col"
      style={{ padding: "var(--card-pad)", gap: "var(--item-gap)" }}
    >
      <div
        className="sticky top-0 z-[2] supports-[backdrop-filter]:backdrop-blur-sm flex items-center justify-between gap-3"
        style={{
          backgroundColor: "color-mix(in oklab, var(--paper-card) 88%, transparent)",
          marginInline: "calc(var(--card-pad) * -1)",
          paddingInline: "var(--card-pad)",
          paddingTop: "calc(var(--card-pad) * 0.6)",
          paddingBottom: "calc(var(--card-pad) * 0.4)",
        }}
      >
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className="h-2 w-2 rounded-full"
            style={{
              background: "var(--accent)",
              boxShadow: "0 0 10px -1px color-mix(in oklab, var(--accent) 65%, transparent)",
            }}
          />
          <h3 className="text-base font-semibold ui-text-primary tracking-tight">活动流</h3>
          <span className="text-[11.5px] font-bold ui-text-muted tracking-[0.10em]">ACTIVITY</span>
        </div>
        <span className="text-[13px] ui-text-muted font-mono tabular-nums font-medium">
          {completed}/{modules.length}
        </span>
      </div>

      {/* 顶部进度条：把 metric ring 的"完成度"在这里再视觉强调一次 */}
      <div className="relative h-[3px] overflow-hidden rounded-full bg-[var(--border-subtle)]">
        <span
          aria-hidden
          className="absolute left-0 top-0 h-full rounded-full ui-motion-base"
          style={{
            width: `${completionRatio * 100}%`,
            background:
              "linear-gradient(90deg, var(--success) 0%, color-mix(in oklab, var(--success) 60%, var(--accent)) 100%)",
          }}
        />
      </div>

      <ol className="relative pl-[22px]">
        {/* 竖线对齐节点中心（左 9px，节点 10px 半径中点） */}
        <span
          aria-hidden
          className="absolute left-[9px] top-2 bottom-2 w-px bg-[var(--border-subtle)]"
        />
        {modules.map((m, idx) => (
          <TimelineRow
            key={m.moduleId}
            index={idx + 1}
            module={m}
            onSelect={() => {
              if (m.isPlaceholder) return;
              onSelectModule(m.moduleId);
            }}
          />
        ))}
      </ol>
    </section>
  );
}

function TimelineRow({
  module: m,
  index,
  onSelect,
}: {
  module: TimelineModule;
  index: number;
  onSelect: () => void;
}) {
  const tone: "completed" | "running" | "idle" = m.status === "completed"
    ? "completed"
    : m.status === "running"
      ? "running"
      : "idle";

  const stepDone = (m.steps ?? []).filter((s) => s.done).length;
  const stepTotal = m.steps?.length ?? 0;
  const counter = stepTotal > 0
    ? `${stepDone.toString().padStart(2, "0")}/${stepTotal.toString().padStart(2, "0")}`
    : tone === "completed"
      ? "DONE"
      : tone === "running"
        ? "··/··"
        : "--/--";

  const labelClass =
    tone === "running"
      ? "ui-text-primary font-semibold"
      : tone === "completed"
        ? "ui-text-secondary"
        : "ui-text-muted";

  const counterClass =
    tone === "running"
      ? "text-[var(--accent)]"
      : tone === "completed"
        ? "text-[var(--success)]"
        : "ui-text-muted";

  const currentLine =
    tone === "running" && m.progressLabel
      ? m.progressLabel
      : tone === "running"
        ? "进行中"
        : null;

  return (
    <li
      className={[
        "relative grid grid-cols-[auto,1fr,auto] items-center gap-3 py-2.5 -ml-[22px] pl-[22px] rounded-lg ui-motion-fast",
        tone === "running" ? "bg-[color-mix(in_oklab,var(--accent)_4%,transparent)]" : "hover:bg-[var(--surface-2)]/40",
      ].join(" ")}
    >
      <span className="relative flex h-5 w-5 items-center justify-center shrink-0 -ml-[26px]">
        <TimelineNode tone={tone} />
      </span>

      <button
        type="button"
        onClick={onSelect}
        disabled={m.isPlaceholder}
        className="flex flex-col items-start text-left min-w-0 ui-motion-fast hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <span className="flex items-center gap-2 max-w-full">
          <span className="text-[12px] font-bold tracking-[0.10em] ui-text-muted font-mono tabular-nums shrink-0">
            {index.toString().padStart(2, "0")}
          </span>
          <span className={`text-[15px] leading-tight truncate ${labelClass}`}>
            {m.label}
          </span>
          {tone === "running" ? (
            <span
              className="text-[11px] font-bold tracking-[0.10em] uppercase shrink-0 px-1.5 py-0.5 rounded-full border"
              style={{
                background: "var(--accent-bg-soft)",
                color: "var(--accent)",
                borderColor: "var(--accent-border)",
              }}
            >
              LIVE
            </span>
          ) : null}
        </span>
        {currentLine ? (
          <span className="text-[13.5px] ui-text-muted truncate max-w-full mt-1">
            <span className="text-[var(--accent)] mr-1">→</span>
            {currentLine}
          </span>
        ) : null}
      </button>

      <span className={`text-[13.5px] font-mono tabular-nums font-medium shrink-0 ${counterClass}`}>
        {counter}
      </span>
    </li>
  );
}

function TimelineNode({ tone }: { tone: "completed" | "running" | "idle" }) {
  // 全部用 currentColor 把背后的竖线"截断"——20×20 的擦除圆 + 实心 / 空心节点
  if (tone === "completed") {
    return (
      <>
        <span
          aria-hidden
          className="absolute inset-0 rounded-full"
          style={{ background: "var(--paper-card)" }}
        />
        <span
          aria-hidden
          className="relative h-2.5 w-2.5 rounded-full"
          style={{
            background: "var(--success)",
            boxShadow: "0 0 0 2px color-mix(in oklab, var(--success) 25%, transparent)",
          }}
        />
      </>
    );
  }
  if (tone === "running") {
    return (
      <>
        <span
          aria-hidden
          className="absolute inset-0 rounded-full"
          style={{ background: "var(--paper-card)" }}
        />
        <span className="relative inline-flex h-3 w-3">
          <span
            aria-hidden
            className="absolute inline-flex h-full w-full rounded-full opacity-50 animate-ping"
            style={{ background: "var(--accent)" }}
          />
          <span
            aria-hidden
            className="relative inline-flex h-3 w-3 rounded-full"
            style={{
              background: "var(--accent)",
              boxShadow:
                "0 0 0 3px color-mix(in oklab, var(--accent) 22%, transparent), 0 0 14px -2px color-mix(in oklab, var(--accent) 60%, transparent)",
            }}
          />
        </span>
      </>
    );
  }
  return (
    <>
      <span
        aria-hidden
        className="absolute inset-0 rounded-full"
        style={{ background: "var(--paper-card)" }}
      />
      <span
        aria-hidden
        className="relative h-2.5 w-2.5 rounded-full bg-[var(--surface-3)] border border-[var(--border-strong)]"
      />
    </>
  );
}
