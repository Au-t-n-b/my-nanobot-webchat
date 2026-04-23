"use client";

import type { FileInsightReport } from "../previewTypes";
import { CodeRenderer } from "./CodeRenderer";

const stubResolution = { path: "", kind: "text" as const, fetch: "none" as const };

function riskBadgeClass(level: FileInsightReport["risk_level"]): string {
  if (level === "danger") {
    return "border-red-500/35 bg-red-500/12 text-red-200";
  }
  if (level === "warning") {
    return "border-amber-500/35 bg-amber-500/12 text-amber-100";
  }
  return "border-emerald-500/30 bg-emerald-500/10 text-emerald-100";
}

function riskLabel(level: FileInsightReport["risk_level"]): string {
  if (level === "danger") return "高风险";
  if (level === "warning") return "注意";
  return "相对安全";
}

export function InsightRenderer(props: { path: string; report: FileInsightReport }) {
  const { path, report } = props;
  const snippets = Array.isArray(report.extracted_snippets) ? report.extracted_snippets : [];

  return (
    <div className="mt-4 space-y-4 rounded-2xl border border-[var(--border-subtle)] bg-[color-mix(in_srgb,var(--surface-2)_88%,transparent)] p-4 shadow-inner">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight ui-text-primary flex items-center gap-2">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--accent)_22%,transparent)] text-[var(--accent)] text-xs">
            AI
          </span>
          文件洞察
        </h3>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${riskBadgeClass(report.risk_level)}`}
        >
          {riskLabel(report.risk_level)}
        </span>
      </div>

      <div className="rounded-xl border border-white/5 bg-black/20 px-3 py-2 text-xs font-mono text-violet-200/90">
        {report.file_type_guess}
      </div>

      <p className="text-sm leading-relaxed ui-text-secondary">{report.summary}</p>

      {snippets.length > 0 ? (
        <div className="space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider ui-text-muted">提取片段</p>
          <div className="space-y-3 max-h-[min(40vh,360px)] overflow-auto pr-1">
            {snippets.map((snippet, i) => (
              <div
                key={`${i}-${snippet.slice(0, 24)}`}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] overflow-hidden"
              >
                <CodeRenderer
                  path={`${path}#insight-snippet-${i}`}
                  resolution={stubResolution}
                  code={snippet}
                  lang="text"
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="rounded-lg border border-[var(--accent)]/20 bg-[color-mix(in_srgb,var(--accent)_8%,transparent)] px-3 py-2 text-sm ui-text-primary">
        <span className="text-[11px] font-semibold uppercase tracking-wider ui-text-muted mr-2">建议</span>
        {report.next_action_suggestion}
      </div>
    </div>
  );
}
