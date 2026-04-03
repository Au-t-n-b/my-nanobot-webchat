"use client";

type Props = {
  headers?: string[];
  rows: string[][];
};

export function SduiTable({ headers, rows }: Props) {
  const safeRows = Array.isArray(rows) ? rows : [];
  return (
    <div className="overflow-auto rounded-lg border" style={{ borderColor: "var(--border-subtle)" }}>
      <table className="text-xs w-full border-collapse ui-text-primary">
        {headers && headers.length > 0 ? (
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th
                  key={i}
                  className="text-left px-2 py-1.5 border-b font-medium ui-text-secondary"
                  style={{ borderColor: "var(--border-subtle)" }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        ) : null}
        <tbody>
          {safeRows.map((row, ri) => (
            <tr key={ri} className="border-b" style={{ borderColor: "var(--border-subtle)" }}>
              {(Array.isArray(row) ? row : []).map((cell, ci) => (
                <td key={ci} className="px-2 py-1 align-top border-r last:border-r-0" style={{ borderColor: "var(--border-subtle)" }}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
