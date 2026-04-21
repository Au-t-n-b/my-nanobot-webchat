"use client";

import { useMemo } from "react";

export type BaseDataGridColumn = { key: string; label: string };
export type BaseDataGridRow = Record<string, unknown>;

export type BaseDataGridProps = {
  id?: string;
  columns: BaseDataGridColumn[];
  rows: BaseDataGridRow[];
  editable?: boolean;
  selectedRowIndex?: number | null;
  onSelectRow?: (index: number, row: BaseDataGridRow) => void;
  onCellChange?: (rowIndex: number, key: string, value: string) => void;
  footer?: React.ReactNode;
};

export function BaseDataGrid({
  columns,
  rows,
  editable = false,
  selectedRowIndex,
  onSelectRow,
  onCellChange,
  footer,
}: BaseDataGridProps) {
  const safeColumns = Array.isArray(columns) ? columns : [];
  const safeRows = Array.isArray(rows) ? rows : [];

  const canSelect = typeof onSelectRow === "function";
  const canEdit = editable && typeof onCellChange === "function";

  const minWidth = useMemo(() => {
    // Keep the same feel as SDUI DataGrid: not too narrow.
    return Math.max(320, safeColumns.length * 140);
  }, [safeColumns.length]);

  return (
    <div className="flex flex-col min-w-0">
      <div className="rounded-xl border border-slate-100 overflow-hidden shadow-sm dark:border-white/5">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse" style={{ minWidth }}>
            <thead>
              <tr className="border-b-2 border-slate-200 dark:border-zinc-700">
                {safeColumns.map((col) => (
                  <th
                    key={col.key}
                    className="bg-slate-50/90 px-4 py-3 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap dark:bg-zinc-800/90 dark:text-zinc-400"
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {safeRows.map((row, ri) => (
                <tr
                  key={ri}
                  className={[
                    "border-b border-slate-50 last:border-0 transition-colors dark:border-zinc-800/50",
                    canSelect ? "hover:bg-slate-50/50 dark:hover:bg-zinc-800/30 cursor-pointer" : "",
                    selectedRowIndex === ri ? "bg-slate-50/70 dark:bg-zinc-800/40" : "",
                  ]
                    .join(" ")
                    .trim()}
                  onClick={() => {
                    if (!canSelect) return;
                    onSelectRow(ri, row);
                  }}
                >
                  {safeColumns.map((col) => {
                    const raw = row[col.key];
                    const display = raw === null || raw === undefined ? "" : String(raw);
                    return (
                      <td key={col.key} className="px-4 py-4 text-sm leading-relaxed text-slate-700 align-top dark:text-zinc-300">
                        {canEdit ? (
                          <input
                            className="w-full bg-transparent border-b border-transparent focus:border-slate-400 focus:outline-none focus:ring-0 px-0 py-1 transition-colors dark:focus:border-zinc-500"
                            value={display}
                            onChange={(e) => onCellChange(ri, col.key, e.target.value)}
                          />
                        ) : (
                          <span className="break-words">{display}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {footer ? (
        <div className="bg-slate-50/50 px-4 py-3 flex justify-end border-t border-slate-100 dark:bg-zinc-800/50 dark:border-white/5">
          {footer}
        </div>
      ) : null}
    </div>
  );
}

