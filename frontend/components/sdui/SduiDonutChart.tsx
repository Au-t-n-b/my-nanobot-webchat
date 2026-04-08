"use client";

import { useMemo } from "react";

import type { SduiDonutSegment } from "@/lib/sdui";
import { isSemanticColor, semanticToCssColorValue } from "@/components/sdui/sduiSemanticColor";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

const DEFAULT_COLORS = [
  "var(--success)",
  "color-mix(in oklab, var(--accent) 75%, var(--surface-2))",
  "var(--warning)",
  "color-mix(in oklab, var(--danger) 70%, var(--surface-2))",
  "color-mix(in oklab, var(--text-muted) 55%, var(--surface-2))",
];

type Props = {
  segments: SduiDonutSegment[];
  centerLabel?: string;
  centerValue?: string;
};

function polar(cx: number, cy: number, r: number, angle: number) {
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
}

/** 从 angle0 扫到 angle1（弧度），圆环扇区 */
function donutSlicePath(
  cx: number,
  cy: number,
  rInner: number,
  rOuter: number,
  angle0: number,
  angle1: number,
): string {
  const largeArc = angle1 - angle0 > Math.PI ? 1 : 0;
  const p0o = polar(cx, cy, rOuter, angle0);
  const p1o = polar(cx, cy, rOuter, angle1);
  const p1i = polar(cx, cy, rInner, angle1);
  const p0i = polar(cx, cy, rInner, angle0);
  return [
    `M ${p0o.x} ${p0o.y}`,
    `A ${rOuter} ${rOuter} 0 ${largeArc} 1 ${p1o.x} ${p1o.y}`,
    `L ${p1i.x} ${p1i.y}`,
    `A ${rInner} ${rInner} 0 ${largeArc} 0 ${p0i.x} ${p0i.y}`,
    "Z",
  ].join(" ");
}

export function SduiDonutChart({ segments, centerLabel, centerValue }: Props) {
  const { postToAgent, openPreview } = useSkillUiRuntime();
  const { paths, total, legend } = useMemo(() => {
    const safe = segments.filter((s) => Number.isFinite(s.value) && s.value > 0);
    const sum = safe.reduce((a, s) => a + s.value, 0);
    if (sum <= 0) {
      return { paths: [] as { d: string; color: string; key: string; action?: SduiDonutSegment["action"] }[], total: 0, legend: safe };
    }
    const cx = 100;
    const cy = 100;
    const rOuter = 52;
    const rInner = 34;
    let angle = -Math.PI / 2;
    const out: { d: string; color: string; key: string; action?: SduiDonutSegment["action"] }[] = [];
    safe.forEach((seg, i) => {
      const sweep = (seg.value / sum) * Math.PI * 2;
      const a0 = angle;
      const a1 = angle + sweep;
      const raw = seg.color;
      const color =
        (isSemanticColor(raw) ? semanticToCssColorValue(raw) : null) ??
        (typeof raw === "string" && raw.trim() ? raw : null) ??
        DEFAULT_COLORS[i % DEFAULT_COLORS.length];
      out.push({
        d: donutSlicePath(cx, cy, rInner, rOuter, a0, a1),
        color,
        key: `${seg.label}-${i}`,
        action: seg.action,
      });
      angle = a1;
    });
    return { paths: out, total: sum, legend: safe };
  }, [segments]);

  if (paths.length === 0) {
    return (
      <div className="flex min-h-[168px] w-full items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-6 text-xs text-[var(--text-muted)]">
        暂无分布数据
      </div>
    );
  }

  return (
    <div className="flex w-full min-w-0 flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative mx-auto flex h-[min(200px,42vw)] w-[min(200px,42vw)] max-w-[220px] shrink-0 items-center justify-center sm:mx-0">
        <svg
          viewBox="0 0 200 200"
          className="h-full w-full drop-shadow-[0_1px_2px_color-mix(in_oklab,var(--surface-0)_40%,transparent)]"
          aria-hidden
        >
          <title>圆环图</title>
          {paths.map((p) => {
            const act = p.action;
            const clickable = Boolean(act && (act.kind === "open_preview" || act.kind === "post_user_message"));
            return (
              <path
                key={p.key}
                d={p.d}
                fill={p.color}
                stroke="var(--surface-1)"
                strokeWidth={1}
                strokeLinejoin="round"
                className={clickable ? "cursor-pointer transition-opacity hover:opacity-85" : undefined}
                onClick={
                  clickable
                    ? () => {
                        if (!act) return;
                        if (act.kind === "open_preview") openPreview(act.path);
                        else if (act.kind === "post_user_message") postToAgent(act.text);
                      }
                    : undefined
                }
              />
            );
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center text-center">
          {centerLabel ? (
            <span className="max-w-[80%] text-[10px] font-medium leading-tight text-[var(--text-muted)] sm:text-xs">
              {centerLabel}
            </span>
          ) : null}
          {centerValue ? (
            <span className="mt-0.5 text-lg font-bold tabular-nums text-[var(--text-primary)] sm:text-xl">{centerValue}</span>
          ) : null}
        </div>
      </div>
      <ul className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs sm:text-[13px]">
        {legend.map((seg, i) => {
          const pct = total > 0 ? Math.round((seg.value / total) * 1000) / 10 : 0;
          const raw = seg.color;
          const c =
            (isSemanticColor(raw) ? semanticToCssColorValue(raw) : null) ??
            (typeof raw === "string" && raw.trim() ? raw : null) ??
            DEFAULT_COLORS[i % DEFAULT_COLORS.length];
          return (
            <li key={`${seg.label}-${i}`} className="flex min-w-0 items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2">
                <svg className="h-3 w-3 shrink-0" viewBox="0 0 10 10" aria-hidden>
                  <rect x="1" y="1" width="8" height="8" rx="1.5" fill={c} stroke="var(--border-subtle)" strokeWidth="1" />
                </svg>
                <span className="truncate text-[var(--text-secondary)]">{seg.label}</span>
              </span>
              <span className="shrink-0 tabular-nums text-[var(--text-primary)]">
                {pct}%
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
