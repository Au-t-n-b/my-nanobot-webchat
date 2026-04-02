"use client";

import type { SkillUiComponentProps } from "@/lib/skillUiRegistry";

/**
 * Skill UI 打样组件：展示从 dataFile 拉取的 JSON。
 * 注册名：SurveySummary（与 skill-ui://SurveySummary 一致）
 */
export function SurveySummary({ data, loading, error, dataFilePath }: SkillUiComponentProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm ui-text-muted py-6">
        <span className="inline-block w-4 h-4 rounded-full border-2 border-t-transparent animate-spin border-[var(--accent)]" />
        加载数据中…
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="rounded-xl p-4 text-sm whitespace-pre-wrap"
        style={{
          border: "1px solid rgba(239,107,115,0.35)",
          background: "rgba(239,107,115,0.08)",
          color: "var(--danger)",
        }}
      >
        {error}
      </div>
    );
  }

  const jsonText =
    data === undefined
      ? "// 未提供 dataFile 或文件为空"
      : JSON.stringify(data, null, 2);

  return (
    <div className="flex flex-col gap-3 min-h-0">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="text-sm font-semibold ui-text-primary">SurveySummary</h3>
        {dataFilePath && (
          <code className="text-[10px] px-2 py-1 rounded-md ui-text-muted truncate max-w-full" title={dataFilePath}>
            {dataFilePath}
          </code>
        )}
      </div>
      <div
        className="rounded-xl border overflow-hidden"
        style={{ borderColor: "var(--border-subtle)", background: "var(--surface-2)" }}
      >
        <pre className="text-[11px] leading-relaxed font-mono p-4 overflow-auto max-h-[min(70vh,560px)] ui-text-secondary">
          {jsonText}
        </pre>
      </div>
      <p className="text-[10px] ui-text-muted">
        Skill UI 示例：数据来自 <code className="ui-text-secondary">dataFile</code> 指向的 JSON。
      </p>
    </div>
  );
}
