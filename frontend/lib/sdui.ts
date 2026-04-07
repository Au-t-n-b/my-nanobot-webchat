/**
 * SDUI（Skill Declarative UI）协议：JSON 文档 → 递归渲染 + 交互回传 Agent。
 * 顶层 skill-ui 仅挂载 `SduiView`；文档内 `root` / `node.type` 驱动原子组件。
 */

import { scanIllegalPresentationKeysForDev } from "./sduiCompliance";

export const SDUI_SCHEMA_VERSION = 1;

/** 间距语义档位（禁止 JSON 中使用自由数字 gap） */
export const SPACING_TOKENS = ["none", "xs", "sm", "md", "lg", "xl"] as const;
export type SpacingToken = (typeof SPACING_TOKENS)[number];

/** v2 语义化颜色（禁止自由色板污染主题） */
export type SduiSemanticColor = "success" | "warning" | "error" | "accent" | "subtle";

/** 支持的原子节点类型（MVP+） */
export type SduiNodeType =
  | "Stack"
  | "Card"
  | "Row"
  | "Divider"
  | "Tabs"
  | "Stepper"
  | "Text"
  | "TextArea"
  | "Markdown"
  | "Badge"
  | "Statistic"
  | "KeyValueList"
  | "Table"
  | "DataGrid"
  | "Button"
  | "Link"
  | "ChartPlaceholder"
  | "DonutChart"
  | "BarChart"
  | "FileKindBadge";

/** 运行时校验 / normalizer 用：全部合法 `type` 字面量 */
export const SDUI_NODE_TYPE_VALUES: readonly SduiNodeType[] = [
  "Stack",
  "Card",
  "Row",
  "Divider",
  "Tabs",
  "Stepper",
  "Text",
  "TextArea",
  "Markdown",
  "Badge",
  "Statistic",
  "KeyValueList",
  "Table",
  "DataGrid",
  "Button",
  "Link",
  "ChartPlaceholder",
  "DonutChart",
  "BarChart",
  "FileKindBadge",
] as const;

/** Tabs 子项图标的封闭枚举（宿主映射到 Lucide，禁止自由 SVG/URL） */
export type SduiTabIconName =
  | "terminal"
  | "clipboardCheck"
  | "alertTriangle"
  | "image"
  | "fileText"
  | "layoutDashboard"
  | "circle";

/** Stepper 每步状态 */
export type SduiStepperStatus = "waiting" | "running" | "done" | "error";

export type SduiAction =
  | { kind: "post_user_message"; text: string }
  | { kind: "open_preview"; path: string };

export type SduiDocument = {
  schemaVersion: number;
  /** 固定为 SduiDocument，便于与内部节点区分 */
  type: "SduiDocument";
  root: SduiNode;
  meta?: Record<string, unknown>;
};

export type SduiNode =
  | SduiStackNode
  | SduiCardNode
  | SduiRowNode
  | SduiDividerNode
  | SduiTabsNode
  | SduiStepperNode
  | SduiTextNode
  | SduiTextAreaNode
  | SduiMarkdownNode
  | SduiBadgeNode
  | SduiStatisticNode
  | SduiKeyValueListNode
  | SduiTableNode
  | SduiDataGridNode
  | SduiButtonNode
  | SduiLinkNode
  | SduiChartPlaceholderNode
  | SduiDonutChartNode
  | SduiBarChartNode
  | SduiFileKindBadgeNode;

/** 各节点可选的稳定 id，用于列表 React key 与排查 */
type SduiOptionalId = {
  id?: string;
  /** v2：布局比例（Row/Stack 等容器按 flex 分配空间） */
  flex?: number;
};

export type SduiStackNode = SduiOptionalId & {
  type: "Stack";
  /** 语义间距档位；禁止数字 */
  gap?: SpacingToken;
  /** v2：主轴对齐（Stack 为纵向 flex-col） */
  justify?: "start" | "center" | "end" | "between";
  children?: SduiNode[];
};

export type SduiCardNode = SduiOptionalId & {
  type: "Card";
  title?: string;
  /** 紧凑布局：更低内边距，适合产物行等列表 */
  density?: "default" | "compact";
  children?: SduiNode[];
};

export type SduiRowNode = SduiOptionalId & {
  type: "Row";
  gap?: SpacingToken;
  align?: "start" | "center" | "end" | "stretch" | "baseline";
  /** 主轴对齐（如产物行左右分布） */
  justify?: "start" | "end" | "center" | "between" | "around";
  wrap?: boolean;
  children?: SduiNode[];
};

export type SduiDividerNode = SduiOptionalId & {
  type: "Divider";
  orientation?: "horizontal" | "vertical";
};

/** 单个 Tab：独立子树，由宿主切换展示 */
export type SduiTabPanel = {
  id: string;
  label: string;
  /** 可选语义图标，见 {@link SduiTabIconName} */
  icon?: SduiTabIconName;
  children?: SduiNode[];
};

export type SduiTabsNode = SduiOptionalId & {
  type: "Tabs";
  /** 至少一项；`id` 在同一 Tabs 内唯一 */
  tabs: SduiTabPanel[];
  /** 初始选中；缺省为第一项 `tabs[0].id` */
  defaultTabId?: string;
};

/** 单个流程步骤（无子树，仅展示状态） */
export type SduiStepperStep = {
  id: string;
  title: string;
  status: SduiStepperStatus;
};

/** 横向/纵向流程步骤条 */
export type SduiStepperNode = SduiOptionalId & {
  type: "Stepper";
  steps: SduiStepperStep[];
  /** 默认横向；纵向时适用于窄栏 */
  orientation?: "horizontal" | "vertical";
};

export type SduiTextNode = SduiOptionalId & {
  type: "Text";
  content: string;
  variant?: "caption" | "body" | "heading" | "mono";
  color?: SduiSemanticColor;
  align?: "start" | "center" | "end";
};

export type SduiTextAreaNode = SduiOptionalId & {
  type: "TextArea";
  /** 与 {{input:xxx}} 占位符 id 对应 */
  inputId: string;
  label?: string;
  placeholder?: string;
  rows?: number;
  defaultValue?: string;
};

export type SduiMarkdownNode = SduiOptionalId & {
  type: "Markdown";
  content: string;
};

export type SduiBadgeNode = SduiOptionalId & {
  type: "Badge";
  /** v1 */
  text?: string;
  tone?: "default" | "success" | "warning" | "danger";
  /** v2 */
  label?: string;
  color?: SduiSemanticColor;
  size?: "sm" | "md";
};

export type SduiStatisticNode = SduiOptionalId & {
  type: "Statistic";
  title: string;
  value: string | number;
  color?: SduiSemanticColor;
};

export type SduiKeyValueListNode = SduiOptionalId & {
  type: "KeyValueList";
  items: Array<{ key: string; value: string; color?: SduiSemanticColor }>;
  color?: SduiSemanticColor;
};

export type SduiTableNode = SduiOptionalId & {
  type: "Table";
  headers?: string[];
  rows: string[][];
};

export type SduiDataGridNode = SduiOptionalId & {
  type: "DataGrid";
  columns: Array<{ key: string; label: string }>;
  rows: Array<Record<string, unknown>>;
  editable?: boolean;
  submitLabel?: string;
  /** 提交时拼在用户消息前的说明前缀 */
  submitActionPrefix?: string;
};

export type SduiButtonNode = SduiOptionalId & {
  type: "Button";
  label: string;
  variant?: "primary" | "secondary" | "ghost" | "outline";
  color?: SduiSemanticColor;
  action: SduiAction;
};

/** 图表占位（饼图/柱状图等），宿主渲染虚线框 + 图标 */
export type SduiChartVariant = "pie" | "bar";

export type SduiChartPlaceholderNode = SduiOptionalId & {
  type: "ChartPlaceholder";
  variant: SduiChartVariant;
  /** 图标下方说明；缺省时由宿主给默认占位句 */
  caption?: string;
};

/** 产物文件类型图标（Word / Excel / PDF / HTML 等） */
export type SduiFileKind = "docx" | "xlsx" | "pdf" | "html" | "other";

export type SduiFileKindBadgeNode = SduiOptionalId & {
  type: "FileKindBadge";
  kind: SduiFileKind;
  /** 产物行等场景使用更大色块图标 */
  size?: "default" | "lg";
};

/** 圆环图扇区 */
export type SduiDonutSegment = {
  label: string;
  value: number;
  /** v2：优先语义色；也允许 hex/rgb/var(...) 回退 */
  color?: SduiSemanticColor | string;
};

export type SduiDonutChartNode = SduiOptionalId & {
  type: "DonutChart";
  segments: SduiDonutSegment[];
  /** 圆心主文案（如「满足度」） */
  centerLabel?: string;
  /** 圆心副文案（如「80%」） */
  centerValue?: string;
};

/** 柱状图数据项 */
export type SduiBarDatum = {
  label: string;
  value: number;
  color?: SduiSemanticColor | string;
};

export type SduiBarChartNode = SduiOptionalId & {
  type: "BarChart";
  data: SduiBarDatum[];
  /** 数值单位后缀，如「项」 */
  valueUnit?: string;
};

export type SduiLinkNode = SduiOptionalId & {
  type: "Link";
  label: string;
  href?: string;
  action?: SduiAction;
};

const INPUT_PLACEHOLDER_RE = /\{\{\s*input\s*:\s*([^}\s]+)\s*\}\}/g;

/**
 * 将 `{{input:someId}}` 替换为当前 TextArea / 输入框中对应 id 的值。
 */
export function expandInputPlaceholders(text: string, getInputValue: (id: string) => string): string {
  return text.replace(INPUT_PLACEHOLDER_RE, (_m, rawId: string) => {
    const id = String(rawId ?? "").trim();
    if (!id) return "";
    return getInputValue(id) ?? "";
  });
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function readNode(raw: unknown): SduiNode | null {
  if (!isRecord(raw)) return null;
  const t = raw.type;
  if (typeof t !== "string" || !t.trim()) return null;
  return raw as SduiNode;
}

/**
 * 校验并解析 SDUI 文档（宽松：缺省字段尽量兜底）。
 *
 * - **合规键剥离**与 **开发期非法键告警**（对 `className` / `style` / `styles` / `css`）由
 *   `normalizeSduiDocumentInput` 在解析前完成；此处额外做一次只读扫描，便于未走 normalizer 的调用方仍能在 development 下看到提示。
 */
export function parseSduiDocument(data: unknown): { ok: true; doc: SduiDocument } | { ok: false; error: string } {
  scanIllegalPresentationKeysForDev(data);

  if (!isRecord(data)) {
    return { ok: false, error: "SDUI 根节点不是对象" };
  }

  const schemaVersion = data.schemaVersion;
  if (typeof schemaVersion !== "number" || !Number.isFinite(schemaVersion)) {
    return { ok: false, error: "缺少或非法的 schemaVersion" };
  }
  if (schemaVersion < 1 || schemaVersion > SDUI_SCHEMA_VERSION) {
    return { ok: false, error: `不支持的 schemaVersion: ${schemaVersion}（当前支持 1–${SDUI_SCHEMA_VERSION}）` };
  }

  const docType = data.type;
  if (docType !== undefined && docType !== "SduiDocument") {
    return { ok: false, error: `文档 type 应为 "SduiDocument"，收到: ${String(docType)}` };
  }

  const root = readNode(data.root);
  if (!root) {
    return { ok: false, error: "缺少有效的 root 节点" };
  }

  const meta = data.meta;
  const doc: SduiDocument = {
    schemaVersion,
    type: "SduiDocument",
    root,
    meta: isRecord(meta) ? meta : undefined,
  };
  return { ok: true, doc };
}
