"use client";

import { useMemo, useState } from "react";
import { BaseDataGrid } from "@/components/dataGrid/BaseDataGrid";
import type { BaseRendererProps } from "../previewTypes";

export type DataGridPayload = {
  sourceText: string;
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, unknown>>;
  isTruncated: boolean;
  warning?: string;
};

export function DataGridRenderer(
  props: BaseRendererProps & {
    payload: DataGridPayload;
    SourceRenderer: React.ComponentType<{ text: string }>;
  }
) {
  const [mode, setMode] = useState<"grid" | "source">("grid");

  const warning = props.payload.isTruncated ? props.payload.warning : undefined;
  const title = useMemo(() => props.path.replace(/\\/g, "/").split("/").pop() ?? props.path, [props.path]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs ui-text-muted truncate">{title}</p>
        </div>
        <div className="shrink-0 flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] p-1">
          <button
            type="button"
            className={[
              "px-2 py-1 text-xs rounded-md transition-colors",
              mode === "grid" ? "bg-[var(--surface-3)] ui-text-primary" : "ui-text-secondary hover:bg-[var(--surface-3)]",
            ].join(" ")}
            onClick={() => setMode("grid")}
          >
            表格模式
          </button>
          <button
            type="button"
            className={[
              "px-2 py-1 text-xs rounded-md transition-colors",
              mode === "source" ? "bg-[var(--surface-3)] ui-text-primary" : "ui-text-secondary hover:bg-[var(--surface-3)]",
            ].join(" ")}
            onClick={() => setMode("source")}
          >
            源码模式
          </button>
        </div>
      </div>

      {warning ? (
        <div
          className="rounded-xl border p-3 text-sm"
          style={{ borderColor: "rgba(245,158,11,0.30)", background: "rgba(245,158,11,0.08)", color: "rgb(245,158,11)" }}
        >
          {warning}
        </div>
      ) : null}

      {mode === "source" ? (
        <props.SourceRenderer text={props.payload.sourceText} />
      ) : (
        <BaseDataGrid columns={props.payload.columns} rows={props.payload.rows} editable={false} />
      )}
    </div>
  );
}

