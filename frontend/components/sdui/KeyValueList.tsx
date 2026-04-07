"use client";

import { Fragment } from "react";

import type { SduiSemanticColor } from "@/lib/sdui";
import { semanticTextClass } from "@/components/sdui/sduiSemanticColor";

type Props = {
  items?: Array<{ key: string; value: string; color?: SduiSemanticColor }> | null;
  color?: SduiSemanticColor;
};

function normalizeItems(raw: Props["items"]): Array<{ key: string; value: string; color?: SduiSemanticColor }> {
  if (!raw || !Array.isArray(raw)) return [];
  return raw
    .filter((it): it is { key: string; value: string } => it != null && typeof it === "object")
    .map((it) => ({
      key: String((it as { key?: unknown }).key ?? ""),
      value: String((it as { value?: unknown }).value ?? ""),
      color: (it as { color?: unknown }).color as SduiSemanticColor | undefined,
    }));
}

export function SduiKeyValueList({ items, color }: Props) {
  const list = normalizeItems(items);
  const baseColor = semanticTextClass(color);
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {list.map((it, i) => (
        <Fragment key={`${it.key}-${i}`}>
          <dt className="ui-text-muted font-medium">{it.key}</dt>
          <dd className={`ui-text-primary min-w-0 break-words ${semanticTextClass(it.color) || baseColor}`.trim()}>
            {it.value}
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}
