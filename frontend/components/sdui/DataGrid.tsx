"use client";

import { useEffect, useMemo, useState } from "react";
import type { SduiDataGridNode } from "@/lib/sdui";
import { useSkillUiRuntime } from "@/components/sdui/SkillUiRuntimeProvider";
import { BaseDataGrid } from "@/components/dataGrid/BaseDataGrid";

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
    <BaseDataGrid
      id={stableId}
      columns={safeColumns}
      rows={rows}
      editable={editable}
      selectedRowIndex={selectedRowIndex}
      onSelectRow={(ri, row) => {
        setSelectedRowIndex(ri);
        syncState({
          key: `datagrid.${stableId}.selectedRow`,
          value: { index: ri, row },
          behavior: "immediate",
        });
      }}
      onCellChange={(ri, key, value) => {
        setCell(ri, key, value);
        syncState({
          key: `datagrid.${stableId}.cells.${ri}.${key}`,
          value,
          behavior: "debounce",
        });
      }}
      footer={
        editable ? (
          <button type="button" className="ui-btn-accent rounded-lg px-3 py-1.5 text-sm font-medium" onClick={submit}>
            {submitLabel}
          </button>
        ) : null
      }
    />
  );
}
