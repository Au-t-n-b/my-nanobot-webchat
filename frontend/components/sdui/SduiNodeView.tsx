"use client";

import type { ReactNode } from "react";
import type {
  SduiNode,
  SduiGuidanceCardNode,
  SduiChoiceCardNode,
  SduiConfirmCardNode,
  SduiGanttChartNode,
  SduiEmbeddedWebNode,
} from "@/lib/sdui";
import { stableChildKey } from "@/lib/sduiKeys";
import { SduiStack } from "@/components/sdui/Stack";
import { SduiCard } from "@/components/sdui/Card";
import { SduiRow } from "@/components/sdui/Row";
import { SduiDivider } from "@/components/sdui/Divider";
import { SduiText } from "@/components/sdui/Text";
import { SduiTextArea } from "@/components/sdui/TextArea";
import { SduiMarkdown } from "@/components/sdui/Markdown";
import { SduiFilePicker } from "@/components/sdui/FilePicker";
import { SduiBadge } from "@/components/sdui/Badge";
import { SduiStatistic } from "@/components/sdui/Statistic";
import { SduiKeyValueList } from "@/components/sdui/KeyValueList";
import { SduiTable } from "@/components/sdui/Table";
import { SduiDataGrid } from "@/components/sdui/DataGrid";
import { SduiButton } from "@/components/sdui/Button";
import { SduiLink } from "@/components/sdui/Link";
import { SduiTabs } from "@/components/sdui/SduiTabs";
import { SduiStepper } from "@/components/sdui/SduiStepper";
import { SduiChartPlaceholder } from "@/components/sdui/SduiChartPlaceholder";
import { SduiGoldenMetrics } from "@/components/sdui/SduiGoldenMetrics";
import { SduiDonutChart } from "@/components/sdui/SduiDonutChart";
import { SduiBarChart } from "@/components/sdui/SduiBarChart";
import { SduiFileKindBadge } from "@/components/sdui/SduiFileKindBadge";
import { SduiArtifactGrid } from "@/components/sdui/SduiArtifactGrid";
import { SduiGuidanceCard } from "@/components/sdui/GuidanceCard";
import { SduiChoiceCard } from "@/components/sdui/ChoiceCard";
import { SduiConfirmCard } from "@/components/sdui/ConfirmCard";
import { SduiStatisticRow } from "@/components/sdui/SduiStatisticRow";
import { SduiGanttLane } from "@/components/sdui/SduiGanttLane";
import { EmbeddedWeb } from "@/components/sdui/EmbeddedWeb";

function UnknownNode({ type }: { type: string }) {
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs text-[var(--text-primary)] border-[color-mix(in_oklab,var(--warning)_35%,transparent)] bg-[color-mix(in_oklab,var(--warning)_8%,var(--surface-2))]"
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
  const inner = (() => {
    switch (node.type) {
    case "Stack":
      return (
        <SduiStack gap={node.gap} justify={node.justify}>
          {node.children?.map((child, i) => {
            const seg = stableChildKey(child, i, pathPrefix);
            return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;
          })}
        </SduiStack>
      );

    case "Card":
      return (
        <SduiCard title={node.title} density={node.density}>
          {node.children?.map((child, i) => {
            const seg = stableChildKey(child, i, pathPrefix);
            return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;
          })}
        </SduiCard>
      );

    case "Row": {
      const rowChildren = node.children ?? [];
      const rowAllStatistic = rowChildren.length > 0 && rowChildren.every((c) => c.type === "Statistic");
      if (rowAllStatistic) {
        return (
          <div className="metrics-grid w-full">
            {rowChildren.map((child, i) => {
              const seg = stableChildKey(child, i, pathPrefix);
              return (
                <div key={seg} className="min-w-0">
                  <SduiNodeView node={child} pathPrefix={seg} />
                </div>
              );
            })}
          </div>
        );
      }
      return (
        <SduiRow gap={node.gap} align={node.align} justify={node.justify} wrap={node.wrap}>
          {rowChildren.map((child, i) => {
            const seg = stableChildKey(child, i, pathPrefix);
            return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;
          })}
        </SduiRow>
      );
    }

    case "Divider":
      return <SduiDivider orientation={node.orientation} />;

    case "Tabs":
      return <SduiTabs tabs={node.tabs} defaultTabId={node.defaultTabId} pathPrefix={pathPrefix} />;

    case "Stepper":
      return <SduiStepper steps={node.steps} orientation={node.orientation} />;

    case "Skeleton": {
      const variant = node.variant ?? "rect";
      const lines = Math.min(8, Math.max(1, typeof node.lines === "number" ? node.lines : 3));
      let block: ReactNode;
      if (variant === "text") {
        block = (
          <div className="flex w-full flex-col gap-2">
            {Array.from({ length: lines }, (_, i) => (
              <div key={i} className="ui-skeleton h-3 w-full rounded-md" />
            ))}
          </div>
        );
      } else if (variant === "row") {
        block = <div className="ui-skeleton h-10 w-full rounded-lg" />;
      } else if (variant === "card") {
        block = <div className="ui-skeleton min-h-[120px] w-full rounded-xl" />;
      } else {
        block = <div className="ui-skeleton h-20 w-full rounded-xl" />;
      }
      const ch = node.children;
      if (Array.isArray(ch) && ch.length) {
        return (
          <div className="flex w-full flex-col gap-3">
            {block}
            {ch.map((child, i) => {
              const seg = stableChildKey(child, i, pathPrefix);
              return <SduiNodeView key={seg} node={child} pathPrefix={seg} />;
            })}
          </div>
        );
      }
      return block;
    }

    case "Text":
      return <SduiText content={node.content} variant={node.variant} color={node.color} align={node.align} />;

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

    case "FilePicker":
      return <SduiFilePicker {...node} />;

    case "Badge":
      return <SduiBadge text={node.text} label={node.label} tone={node.tone} color={node.color} size={node.size} />;

    case "Statistic":
      return <SduiStatistic title={node.title} value={node.value} color={node.color} />;

    case "KeyValueList":
      return <SduiKeyValueList items={node.items} color={node.color} />;

    case "Table":
      return <SduiTable headers={node.headers} rows={node.rows} />;

    case "DataGrid":
      return <SduiDataGrid {...node} />;

    case "Button":
      return <SduiButton label={node.label} variant={node.variant} color={node.color} action={node.action} />;

    case "Link":
      return <SduiLink label={node.label} href={node.href} action={node.action} />;

    case "ChartPlaceholder":
      return <SduiChartPlaceholder variant={node.variant} caption={node.caption} />;

    case "GoldenMetrics":
      return <SduiGoldenMetrics metrics={(node as { metrics?: Array<{ id?: string; label?: string; value?: number | string; color?: string }> }).metrics} />;

    case "DonutChart":
      return (
        <SduiDonutChart
          segments={node.segments}
          centerLabel={node.centerLabel}
          centerValue={node.centerValue}
        />
      );

    case "BarChart":
      return <SduiBarChart data={node.data} valueUnit={node.valueUnit} />;

    case "FileKindBadge":
      return <SduiFileKindBadge kind={node.kind} size={node.size} />;

    case "ArtifactGrid":
      return <SduiArtifactGrid artifacts={node.artifacts} mode={node.mode} title={node.title} />;

    case "GuidanceCard":
      return (
        <SduiGuidanceCard
          context={node.context}
          actions={node.actions}
          cardId={(node as SduiGuidanceCardNode & { cardId?: string }).cardId}
        />
      );

    case "ChoiceCard":
      return (
        <SduiChoiceCard
          title={node.title}
          options={node.options}
          cardId={(node as SduiChoiceCardNode & { cardId?: string }).cardId}
          hitlRequestId={node.hitlRequestId}
          moduleId={node.moduleId}
          nextAction={node.nextAction}
          skillName={node.skillName}
          stateNamespace={node.stateNamespace}
          stepId={node.stepId}
        />
      );

    case "ConfirmCard": {
      const cn = node as SduiConfirmCardNode & { cardId?: string };
      return (
        <SduiConfirmCard
          title={cn.title}
          confirmLabel={cn.confirmLabel}
          cancelLabel={cn.cancelLabel}
          cardId={cn.cardId}
          hitlRequestId={cn.hitlRequestId}
          moduleId={cn.moduleId}
          nextAction={cn.nextAction}
          skillName={cn.skillName}
          stateNamespace={cn.stateNamespace}
          stepId={cn.stepId}
        />
      );
    }

    case "StatisticRow":
      return <SduiStatisticRow items={node.items} />;

    case "GanttLane":
      return <SduiGanttLane title={node.title} caption={node.caption} lanes={node.lanes} />;

    case "GanttChart": {
      const g = node as SduiGanttChartNode;
      if (g.lanes?.length) {
        return <SduiGanttLane title={g.title} caption={g.caption} lanes={g.lanes} />;
      }
      return <SduiChartPlaceholder variant="bar" caption={g.caption ?? "甘特 / 时间线（数据就绪后展示）"} />;
    }

    case "EmbeddedWeb": {
      const ew = node as SduiEmbeddedWebNode;
      const src = typeof ew.src === "string" ? ew.src.trim() : "";
      if (!src) {
        return <UnknownNode type="EmbeddedWeb (missing src)" />;
      }
      const eid = ew.id?.trim() || ew.embedId?.trim() || "embedded-web";
      return (
        <EmbeddedWeb
          src={src}
          id={eid}
          state={ew.state ?? {}}
          allowedOrigins={ew.allowedOrigins}
          minHeight={ew.minHeight}
          embedSandbox={ew.embedSandbox !== false}
        />
      );
    }

    default:
      return <UnknownNode type={(node as { type?: string }).type ?? "?"} />;
    }
  })();

  const isPartial = (node as unknown as { _partial?: boolean })._partial === true;
  const wrapped = (
    <div className={isPartial ? "sdui-patch-target sdui-partial" : "sdui-patch-target"}>{inner}</div>
  );

  if (typeof node.flex === "number" && Number.isFinite(node.flex) && node.flex > 0) {
    // v2：布局比例（允许 inline style，仅用于 flex 分配）
    const f = node.flex;
    return (
      <div className="min-w-0" style={{ flex: `${f} ${f} 0%` }}>
        {wrapped}
      </div>
    );
  }

  return wrapped;
}
