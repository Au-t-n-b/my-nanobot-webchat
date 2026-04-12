"use client";

import { useEffect, useMemo, useState } from "react";
import type { SduiDataGridNode } from "@/lib/sdui";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";

type Props = SduiDataGridNode;

function cloneRows(rows: Array<Record<string, unknown>> | undefined | null): Array<Record<string, unknown>> {
  if (!rows || !Array.isArray(rows)) return [];
  return rows.map((r) => (r && typeof r === "object" && !Array.isArray(r) ? { ...r } : {}));
}

export function SduiDataGrid({
  id,
  columns,
  rows: initialRows,
  editable = true,
  submitLabel = "提交",
  submitActionPrefix,
}: Props) {
  const { postToAgent, syncState } = useSkillUiRuntime();
  const [rows, setRows] = useState(() => cloneRows(initialRows));
  const [selectedRowIndex, setSelectedRowIndex] = useState<number | null>(null);
  const stableId = useMemo(() => (typeof id === "string" && id.trim() ? id.trim() : "_sdui_datagrid"), [id]);

  useEffect(() => {
    setRows(cloneRows(initialRows));
  }, [initialRows]);

  const safeColumns = Array.isArray(columns) ? columns : [];

  const setCell = (ri: number, key: string, value: string) => {
    setRows((prev) => {
      const next = prev.map((r, i) => (i === ri ? { ...r, [key]: value } : r));
      return next;
    });
  };

  const submit = () => {
    const json = JSON.stringify(rows, null, 2);
    const msg = submitActionPrefix
      ? `${submitActionPrefix}\n\`\`\`json\n${json}\n\`\`\``
      : `\`\`\`json\n${json}\n\`\`\``;
    postToAgent(msg);
  };

  return (
    <div className="flex flex-col min-w-0">
      <div className="rounded-xl border border-slate-100 overflow-hidden shadow-sm dark:border-white/5">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse min-w-[320px]">
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
              {rows.map((row, ri) => (
                <tr
                  key={ri}
                  className={[
                    "border-b border-slate-50 last:border-0 hover:bg-slate-50/50 transition-colors dark:border-zinc-800/50 dark:hover:bg-zinc-800/30",
                    selectedRowIndex === ri ? "bg-slate-50/70 dark:bg-zinc-800/40" : "",
                  ]
                    .join(" ")
                    .trim()}
                  onClick={() => {
                    setSelectedRowIndex(ri);
                    syncState({
                      key: `datagrid.${stableId}.selectedRow`,
                      value: { index: ri, row },
                      behavior: "immediate",
                    });
                  }}
                >
                  {safeColumns.map((col) => {
                    const raw = row[col.key];
                    const display = raw === null || raw === undefined ? "" : String(raw);
                    return (
                      <td key={col.key} className="px-4 py-4 text-sm leading-relaxed text-slate-700 align-top dark:text-zinc-300">
                        {editable ? (
                          <input
                            className="w-full bg-transparent border-b border-transparent focus:border-slate-400 focus:outline-none focus:ring-0 px-0 py-1 transition-colors dark:focus:border-zinc-500"
                            value={display}
                            onChange={(e) => {
                              const v = e.target.value;
                              setCell(ri, col.key, v);
                              syncState({
                                key: `datagrid.${stableId}.cells.${ri}.${col.key}`,
                                value: v,
                                behavior: "debounce",
                              });
                            }}
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
      {editable ? (
        <div className="bg-slate-50/50 px-4 py-3 flex justify-end border-t border-slate-100 dark:bg-zinc-800/50 dark:border-white/5">
          <button type="button" className="ui-btn-accent rounded-lg px-3 py-1.5 text-sm font-medium" onClick={submit}>
            {submitLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}
