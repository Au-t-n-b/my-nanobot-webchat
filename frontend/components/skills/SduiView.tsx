"use client";

import type { SkillUiComponentProps } from "@/lib/skillUiRegistry";
import { parseSduiDocument } from "@/lib/sdui";
import { normalizeSduiDocumentInput } from "@/lib/sduiNormalizer";
import { SduiNodeView } from "@/components/sdui/SduiNodeView";

export function SduiView({ data, loading, error, dataFilePath }: SkillUiComponentProps) {
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm ui-text-muted py-6">
        <span className="inline-block w-4 h-4 rounded-full border-2 border-t-transparent animate-spin border-[var(--accent)]" />
        加载 SDUI 数据中…
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

  if (data === undefined) {
    return (
      <p className="text-sm ui-text-muted py-4">
        未提供 dataFile 或文件为空。请确认 Agent 已输出{" "}
        <code className="ui-text-secondary">[RENDER_UI](skill-ui://SduiView?dataFile=...)</code>
      </p>
    );
  }

  const normalized = normalizeSduiDocumentInput(data);
  const parsed = parseSduiDocument(normalized);
  if (!parsed.ok) {
    return (
      <div
        className="rounded-xl p-4 text-sm space-y-2"
        style={{
          border: "1px solid rgba(245,158,11,0.35)",
          background: "rgba(245,158,11,0.06)",
          color: "rgb(253 230 138)",
        }}
      >
        <p className="font-medium">SDUI 文档无效</p>
        <p className="ui-text-secondary text-xs whitespace-pre-wrap">{parsed.error}</p>
        {dataFilePath ? (
          <p className="text-[10px] ui-text-muted truncate" title={dataFilePath}>
            {dataFilePath}
          </p>
        ) : null}
      </div>
    );
  }

  const meta = parsed.doc.meta;
  const isDashboardChromeHidden =
    meta !== null &&
    typeof meta === "object" &&
    (meta as { role?: string }).role === "dashboard";

  return (
    <div className="flex flex-col gap-3 min-h-0 min-w-0">
      {!isDashboardChromeHidden ? (
        <div className="flex items-center justify-between gap-2 flex-wrap shrink-0">
          <h3 className="text-sm font-semibold ui-text-primary">Skill UI · SDUI</h3>
          {dataFilePath ? (
            <code className="text-[10px] px-2 py-1 rounded-md ui-text-muted truncate max-w-full" title={dataFilePath}>
              {dataFilePath}
            </code>
          ) : null}
        </div>
      ) : null}
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <SduiNodeView node={parsed.doc.root} />
      </div>
    </div>
  );
}
