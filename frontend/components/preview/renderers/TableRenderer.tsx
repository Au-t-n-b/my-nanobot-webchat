"use client";

import type { BaseRendererProps } from "../previewTypes";

export function TableRenderer(props: BaseRendererProps & { rows: string[][] }) {
  return (
    <div className="overflow-auto border border-[var(--border-subtle)] rounded-xl">
      <table className="text-xs ui-text-primary border-collapse w-full">
        <tbody>
          {props.rows.map((row, i) => (
            <tr key={i} className="border-b border-[var(--border-subtle)]">
              {row.map((cell, j) => (
                <td key={j} className="border-r border-[var(--border-subtle)] px-2 py-1 align-top">
                  {String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

