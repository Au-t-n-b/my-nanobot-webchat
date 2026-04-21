"use client";

import { useMemo, useState } from "react";
import { BaseDataGrid } from "@/components/dataGrid/BaseDataGrid";
import type { BaseRendererProps } from "../previewTypes";

export type XlsxPayload = {
  sheets: Array<{
    name: string;
    rows: string[][];
    isTruncated: boolean;
    warning?: string;
  }>;
};

function rowsToGrid(rows: string[][]): { columns: Array<{ key: string; label: string }>; data: Array<Record<string, unknown>> } {
  const header = rows[0] ?? [];
  const body = rows.slice(1);
  const cols = header.map((h, idx) => ({ key: `c${idx + 1}`, label: (h ?? "").toString().trim() || `col_${idx + 1}` }));
  const columns = cols.length ? cols : [{ key: "c1", label: "value" }];
  const data = body.map((r) => {
    const obj: Record<string, unknown> = {};
    for (let i = 0; i < columns.length; i++) obj[columns[i]!.key] = r[i] ?? "";
    return obj;
  });
  return { columns, data };
}

export function XlsxRenderer(props: BaseRendererProps & { payload: XlsxPayload }) {
  const sheets = props.payload.sheets ?? [];
  const [active, setActive] = useState(0);
  const activeSheet = sheets[active] ?? sheets[0];

  const grid = useMemo(() => {
    if (!activeSheet) return null;
    return rowsToGrid(activeSheet.rows);
  }, [activeSheet]);

  if (!activeSheet || !grid) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 overflow-x-auto">
        {sheets.map((s, idx) => {
          const selected = idx === active;
          return (
            <button
              key={`${s.name}-${idx}`}
              type="button"
              onClick={() => setActive(idx)}
              className={[
                "shrink-0 rounded-md border px-2 py-1 text-xs transition-colors",
                selected
                  ? "border-[var(--accent)] bg-[var(--surface-2)] ui-text-primary"
                  : "border-transparent bg-transparent ui-text-secondary hover:bg-[var(--surface-2)]",
              ].join(" ")}
              title={s.name}
            >
              {s.name}
            </button>
          );
        })}
      </div>

      {activeSheet.isTruncated ? (
        <div
          className="rounded-xl border p-3 text-sm"
          style={{ borderColor: "rgba(245,158,11,0.30)", background: "rgba(245,158,11,0.08)", color: "rgb(245,158,11)" }}
        >
          {activeSheet.warning ?? "⚠️ 预览已截断：仅展示前 1000 行 / 50 列。请下载原文件查看完整数据。"}
        </div>
      ) : null}

      <BaseDataGrid columns={grid.columns} rows={grid.data} editable={false} />
    </div>
  );
}

