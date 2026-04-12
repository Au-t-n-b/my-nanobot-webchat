"use client";

import { useMemo } from "react";

import type { SduiDonutSegment } from "@/lib/sdui";
import { normalizeDonutSegments } from "@/lib/sduiDonutChart";
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
  segments?: SduiDonutSegment[] | null;
  centerLabel?: string;
  centerValue?: string;
};

export function SduiDonutChart({ segments, centerLabel, centerValue }: Props) {
  const { postToAgent, openPreview } = useSkillUiRuntime();
  const { rings, total, legend, radius, strokeWidth } = useMemo(() => {
    const safe = normalizeDonutSegments(segments) as SduiDonutSegment[];
    const sum = safe.reduce((a, s) => a + s.value, 0);
    const r = 43;
    const sw = 18;
    const circ = 2 * Math.PI * r;
    if (sum <= 0) {
      return {
        rings: [] as Array<{
          color: string;
          key: string;
          action?: SduiDonutSegment["action"];
          dashArray: string;
          dashOffset: number;
        }>,
        total: 0,
        legend: safe,
        radius: r,
        strokeWidth: sw,
      };
    }
    let offset = 0;
    const out: Array<{
      color: string;
      key: string;
      action?: SduiDonutSegment["action"];
      dashArray: string;
      dashOffset: number;
    }> = [];
    safe.forEach((seg, i) => {
      const raw = seg.color;
      const color =
        (isSemanticColor(raw) ? semanticToCssColorValue(raw) : null) ??
        (typeof raw === "string" && raw.trim() ? raw : null) ??
        DEFAULT_COLORS[i % DEFAULT_COLORS.length];
      const arc = (seg.value / sum) * circ;
      out.push({
        color,
        key: `${seg.label}-${i}`,
        action: seg.action,
        dashArray: `${arc} ${Math.max(circ - arc, 0)}`,
        dashOffset: -offset,
      });
      offset += arc;
    });
    return { rings: out, total: sum, legend: safe, radius: r, strokeWidth: sw };
  }, [segments]);

  if (rings.length === 0) {
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
          <circle
            cx="100"
            cy="100"
            r={radius}
            fill="none"
            stroke="color-mix(in oklab, var(--border-subtle) 75%, var(--surface-2))"
            strokeWidth={strokeWidth}
          />
          <g transform="rotate(-90 100 100)">
            {rings.map((ring) => {
              const act = ring.action;
              const clickable = Boolean(act && (act.kind === "open_preview" || act.kind === "post_user_message"));
              return (
                <circle
                  key={ring.key}
                  cx="100"
                  cy="100"
                  r={radius}
                  fill="none"
                  stroke={ring.color}
                  strokeWidth={strokeWidth}
                  strokeLinecap="round"
                  strokeDasharray={ring.dashArray}
                  strokeDashoffset={ring.dashOffset}
                  className={[
                    "sdui-transition-fill",
                    clickable ? "cursor-pointer hover:opacity-85" : "",
                  ].join(" ").trim() || undefined}
                  style={{
                    transition:
                      "stroke-dasharray 420ms cubic-bezier(0.4, 0, 0.2, 1), stroke-dashoffset 420ms cubic-bezier(0.4, 0, 0.2, 1), stroke 280ms ease, opacity 280ms ease",
                    transformOrigin: "50% 50%",
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
              );
            })}
          </g>
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
