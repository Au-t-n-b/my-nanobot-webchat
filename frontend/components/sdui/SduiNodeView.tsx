"use client";



import type { SduiNode } from "@/lib/sdui";

import { stableChildKey } from "@/lib/sduiKeys";

import { SduiStack } from "@/components/sdui/Stack";

import { SduiCard } from "@/components/sdui/Card";

import { SduiRow } from "@/components/sdui/Row";

import { SduiDivider } from "@/components/sdui/Divider";

import { SduiText } from "@/components/sdui/Text";

import { SduiTextArea } from "@/components/sdui/TextArea";

import { SduiMarkdown } from "@/components/sdui/Markdown";

import { SduiBadge } from "@/components/sdui/Badge";

import { SduiStatistic } from "@/components/sdui/Statistic";

import { SduiKeyValueList } from "@/components/sdui/KeyValueList";

import { SduiTable } from "@/components/sdui/Table";

import { SduiDataGrid } from "@/components/sdui/DataGrid";

import { SduiButton } from "@/components/sdui/Button";

import { SduiLink } from "@/components/sdui/Link";

import { SduiTabs } from "@/components/sdui/SduiTabs";

import { SduiStepper } from "@/components/sdui/SduiStepper";



function UnknownNode({ type }: { type: string }) {

  return (

    <div

      className="rounded-lg border px-3 py-2 text-xs"

      style={{ borderColor: "rgba(245,158,11,0.35)", background: "rgba(245,158,11,0.06)", color: "rgb(253 230 138)" }}

    >

      未知 SDUI 节点类型：<code className="font-mono">{type}</code>

    </div>

  );

}



type Props = {

  node: SduiNode;

  /** 树内路径前缀，用于生成稳定子 key */

  pathPrefix?: string;

};



export function SduiNodeView({ node, pathPrefix = "root" }: Props) {

  switch (node.type) {

    case "Stack":

      return (

        <SduiStack gap={node.gap}>

          {node.children?.map((child, i) => {

            const seg = stableChildKey(child, i, pathPrefix);

            return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;

          })}

        </SduiStack>

      );

    case "Card":

      return (

        <SduiCard title={node.title}>

          {node.children?.map((child, i) => {

            const seg = stableChildKey(child, i, pathPrefix);

            return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;

          })}

        </SduiCard>

      );

    case "Row": {
      const rowChildren = node.children ?? [];
      const rowAllStatistic = rowChildren.length > 0 && rowChildren.every((c) => c.type === "Statistic");
      return (
        <SduiRow gap={node.gap} align={node.align} wrap={node.wrap}>
          {rowChildren.map((child, i) => {
            const seg = stableChildKey(child, i, pathPrefix);
            const inner = <SduiNodeView node={child} pathPrefix={seg} />;
            if (rowAllStatistic) {
              return (
                <div key={seg} className="min-w-0 flex-1 basis-0">
                  {inner}
                </div>
              );
            }
            return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;
          })}
        </SduiRow>
      );
    }

    case "Divider":

      return <SduiDivider />;

    case "Tabs":

      return (
        <SduiTabs
          tabs={node.tabs}
          defaultTabId={node.defaultTabId}
          pathPrefix={pathPrefix}
        />
      );

    case "Stepper":

      return <SduiStepper steps={node.steps} orientation={node.orientation} />;

    case "Text":

      return <SduiText content={node.content} variant={node.variant} />;

    case "TextArea":

      return (

        <SduiTextArea

          inputId={node.inputId}

          label={node.label}

          placeholder={node.placeholder}

          rows={node.rows}

          defaultValue={node.defaultValue}

        />

      );

    case "Markdown":

      return <SduiMarkdown content={node.content} />;

    case "Badge":

      return <SduiBadge text={node.text} tone={node.tone} />;

    case "Statistic":

      return <SduiStatistic title={node.title} value={node.value} />;

    case "KeyValueList":

      return <SduiKeyValueList items={node.items} />;

    case "Table":

      return <SduiTable headers={node.headers} rows={node.rows} />;

    case "DataGrid":

      return <SduiDataGrid {...node} />;

    case "Button":

      return <SduiButton label={node.label} variant={node.variant} action={node.action} />;

    case "Link":

      return <SduiLink label={node.label} href={node.href} action={node.action} />;

    default:

      return <UnknownNode type={(node as { type?: string }).type ?? "?"} />;

  }

}


