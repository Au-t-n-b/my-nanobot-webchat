"use client";

import { useMemo } from "react";

import type { SduiBarDatum } from "@/lib/sdui";
import { isSemanticColor, semanticToCssColorValue } from "@/components/sdui/sduiSemanticColor";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

const DEFAULT_BAR_COLORS = [
  "color-mix(in oklab, var(--accent) 70%, var(--surface-2))",
  "var(--success)",
  "var(--warning)",
  "color-mix(in oklab, var(--danger) 65%, var(--surface-2))",
  "color-mix(in oklab, var(--text-muted) 50%, var(--surface-2))",
];

type Props = {
  data?: SduiBarDatum[] | null;
  valueUnit?: string;
};

export function SduiBarChart({ data, valueUnit }: Props) {
  const { postToAgent, openPreview } = useSkillUiRuntime();
  const { rows, max } = useMemo(() => {
    const list = Array.isArray(data) ? data : [];
    const safe = list.filter((d) => Number.isFinite(d.value));
    const m = Math.max(1, ...safe.map((d) => d.value));
    return { rows: safe, max: m };
  }, [data]);

  if (rows.length === 0) {
    return (
      <div className="flex min-h-[140px] w-full items-center justify-center rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-2)] px-4 py-6 text-xs text-[var(--text-muted)]">
        暂无分类数据
      </div>
    );
  }

  const unit = valueUnit ?? "";

  const W = 420;
  const H = 160;
  const paddingX = 18;
  const paddingTop = 12;
  const paddingBottom = 34;
  const plotH = H - paddingTop - paddingBottom;
  const gap = 10;
  const barW = rows.length > 0 ? Math.max(10, (W - paddingX * 2 - gap * (rows.length - 1)) / rows.length) : 10;

  return (
    <div className="flex w-full min-w-0 flex-col gap-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-2)] p-2" aria-label="柱状图">
        <title>柱状图</title>
        {/* baseline */}
        <line x1={paddingX} y1={paddingTop + plotH} x2={W - paddingX} y2={paddingTop + plotH} stroke="var(--border-subtle)" strokeWidth="1" />
        {rows.map((d, i) => {
          const ratio = max > 0 ? Math.max(0, d.value / max) : 0;
          const h = Math.max(4, Math.round(plotH * ratio));
          const x = paddingX + i * (barW + gap);
          const y = paddingTop + (plotH - h);
          const raw = d.color;
          const fill =
            (isSemanticColor(raw) ? semanticToCssColorValue(raw) : null) ??
            (typeof raw === "string" && raw.trim() ? raw : null) ??
            DEFAULT_BAR_COLORS[i % DEFAULT_BAR_COLORS.length];
          const act = d.action;
          const clickable = Boolean(act && (act.kind === "open_preview" || act.kind === "post_user_message"));

          return (
            <g key={`${d.label}-${i}`}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={h}
                rx={6}
                fill={fill}
                className={[
                  "sdui-transition-fill",
                  clickable ? "cursor-pointer hover:opacity-85" : "",
                ].join(" ").trim() || undefined}
                style={{
                  transition:
                    "x 420ms cubic-bezier(0.4, 0, 0.2, 1), y 420ms cubic-bezier(0.4, 0, 0.2, 1), height 420ms cubic-bezier(0.4, 0, 0.2, 1), fill 280ms ease, opacity 280ms ease",
                }}
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
              <title>{`${d.label}: ${d.value}${unit}`}</title>
              {/* label */}
              <text
                x={x + barW / 2}
                y={H - 12}
                textAnchor="middle"
                fontSize="10"
                fill="var(--text-muted)"
              >
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>

      <div className="flex flex-wrap gap-x-3 gap-y-1 border-t border-[var(--border-subtle)] pt-2 text-[11px] text-[var(--text-secondary)]">
        {rows.map((d, i) => (
          <span key={`sum-${d.label}-${i}`} className="tabular-nums">
            <span className="text-[var(--text-muted)]">{d.label}</span>{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {d.value}
              {unit}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
