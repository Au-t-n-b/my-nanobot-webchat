"use client";

import { Fragment } from "react";

type Props = {
  items?: Array<{ key: string; value: string }> | null;
};

function normalizeItems(raw: Props["items"]): Array<{ key: string; value: string }> {
  if (!raw || !Array.isArray(raw)) return [];
  return raw
    .filter((it): it is { key: string; value: string } => it != null && typeof it === "object")
    .map((it) => ({
      key: String((it as { key?: unknown }).key ?? ""),
      value: String((it as { value?: unknown }).value ?? ""),
    }));
}

export function SduiKeyValueList({ items }: Props) {
  const list = normalizeItems(items);
  return (
    <dl className="grid gap-x-4 gap-y-1 text-sm" style={{ gridTemplateColumns: "auto 1fr" }}>
      {list.map((it, i) => (
        <Fragment key={`${it.key}-${i}`}>
          <dt className="ui-text-muted font-medium">{it.key}</dt>
          <dd className="ui-text-primary min-w-0 break-words">{it.value}</dd>
        </Fragment>
      ))}
    </dl>
  );
}
