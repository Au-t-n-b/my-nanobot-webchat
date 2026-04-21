"use client";

import { useEffect, useMemo, useState } from "react";
import { BaseDataGrid } from "@/components/dataGrid/BaseDataGrid";
import type { BaseRendererProps } from "../previewTypes";

export type XlsxPayload = {
  sheets: Array<{
    name: string;
    rows: string[][];
    isTruncated: boolean;
    totalRows?: number;
    totalColumns?: number;
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
  const [activeName, setActiveName] = useState<string | null>(sheets[0]?.name ?? null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!sheets.length) {
      setActiveName(null);
      return;
    }
    if (activeName && sheets.some((s) => s.name === activeName)) return;
    setActiveName(sheets[0]!.name);
  }, [activeName, sheets]);

  const filteredSheets = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sheets;
    return sheets.filter((s) => s.name.toLowerCase().includes(q));
  }, [query, sheets]);

  const activeSheet = useMemo(() => {
    if (!filteredSheets.length) return null;
    if (activeName) {
      const hit = filteredSheets.find((s) => s.name === activeName);
      if (hit) return hit;
    }
    return filteredSheets[0] ?? null;
  }, [activeName, filteredSheets]);

  const grid = useMemo(() => {
    if (!activeSheet) return null;
    return rowsToGrid(activeSheet.rows);
  }, [activeSheet]);

  if (!activeSheet || !grid) return null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-2 overflow-x-auto min-w-0">
          {filteredSheets.map((s) => {
            const selected = s.name === activeSheet.name;
            const meta =
              typeof s.totalRows === "number" && typeof s.totalColumns === "number"
                ? `${s.totalRows}×${s.totalColumns}`
                : null;
          return (
            <button
              key={s.name}
              type="button"
              onClick={() => setActiveName(s.name)}
              className={[
                "shrink-0 rounded-md border px-2 py-1 text-xs transition-colors",
                selected
                  ? "border-[var(--accent)] bg-[var(--surface-2)] ui-text-primary"
                  : "border-transparent bg-transparent ui-text-secondary hover:bg-[var(--surface-2)]",
              ].join(" ")}
              title={s.name}
            >
              <span className="inline-flex items-center gap-1">
                <span className="truncate max-w-[10rem]">{s.name}</span>
                {s.isTruncated ? <span title="已截断">⚠️</span> : null}
                {meta ? <span className="ui-text-muted">({meta})</span> : null}
              </span>
            </button>
          );
        })}
        </div>

        {sheets.length >= 6 ? (
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索 Sheet…"
            className="shrink-0 w-[160px] rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1 text-xs ui-text-secondary focus:outline-none focus:ring-0 focus:border-[var(--accent)]"
          />
        ) : null}
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

