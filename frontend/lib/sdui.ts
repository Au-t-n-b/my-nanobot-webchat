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

/** Milestone D: 隐式 UI State 同步载荷类型（避免 any 扩散） */
export type UiStateValue = unknown;

/** 支持的原子节点类型（MVP+） */
export type SduiNodeType =
  | "Stack"
  | "Card"
  | "Row"
  | "Divider"
  | "Tabs"
  | "Stepper"
  | "Skeleton"
  | "Text"
  | "TextArea"
  | "Markdown"
  | "FilePicker"
  | "Badge"
  | "Statistic"
  | "KeyValueList"
  | "Table"
  | "DataGrid"
  | "Button"
  | "Link"
  | "ChartPlaceholder"
  | "GoldenMetrics"
  | "DonutChart"
  | "BarChart"
  | "FileKindBadge"
  | "ArtifactGrid"
  | "GuidanceCard"
  | "ChoiceCard"
  | "StatisticRow"
  | "GanttLane"
  | "GanttChart";

/** 运行时校验 / normalizer 用：全部合法 `type` 字面量 */
export const SDUI_NODE_TYPE_VALUES: readonly SduiNodeType[] = [
  "Stack",
  "Card",
  "Row",
  "Divider",
  "Tabs",
  "Stepper",
  "Skeleton",
  "Text",
  "TextArea",
  "Markdown",
  "FilePicker",
  "Badge",
  "Statistic",
  "KeyValueList",
  "Table",
  "DataGrid",
  "Button",
  "Link",
  "ChartPlaceholder",
  "GoldenMetrics",
  "DonutChart",
  "BarChart",
  "FileKindBadge",
  "ArtifactGrid",
  "GuidanceCard",
  "ChoiceCard",
  "StatisticRow",
  "GanttLane",
  "GanttChart",
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

/** Stepper 子步骤（Tooltip 展示用；兼容旧 string 与新结构化项） */
export type SduiStepperDetailItem =
  | string
  | {
      title: string;
      status: SduiStepperStatus;
    };

export type SduiAction =
  | { kind: "post_user_message"; text: string }
  | { kind: "open_preview"; path: string }
  | { kind: "sync_state"; key: string; value: UiStateValue; behavior?: "debounce" | "immediate" }
  | { kind: "chat_card_intent"; verb: string; cardId: string; payload?: unknown };

/**
 * v3 (Milestone-1): Patch envelope for incremental updates.
 * - Only supports `target.by="id"` addressing.
 * - Intended for leaf-field updates (do not change structural children/tabs in M1).
 */
export type SduiPatch = {
  schemaVersion: 3;
  type: "SduiPatch";
  /** 逻辑文档 id（如工勘大盘 `dashboard:gc`），与 revision 一起用于防串台与回放 */
  docId: string;
  baseRevision?: number;
  /** 单调递增；宿主丢弃不大于已应用值的补丁 */
  revision: number;
  /**
   * v3 Visual Stream (M2):
   * - true: 流式片段（可呈现轻微 skeleton/pulse）
   * - false: 稳定状态（结束流式、清理视觉态）
   */
  isPartial?: boolean;
  ops: Array<
    | { op: "merge"; target: { by: "id"; nodeId: string }; value: Partial<SduiNode> & { type: SduiNodeType; id?: string } }
    | { op: "replace"; target: { by: "id"; nodeId: string }; value: SduiNode }
    | { op: "remove"; target: { by: "id"; nodeId: string } }
    | {
        op: "append";
        target: { by: "id"; nodeId: string; field: "children" | "rows" | "artifacts" };
        value: unknown;
      }
  >;
};

export type SduiDocument = {
  schemaVersion: number;
  /** 固定为 SduiDocument，便于与内部节点区分 */
  type: "SduiDocument";
  root: SduiNode;
  meta?: Record<string, unknown>;
};

/** SSE 事件名（与后端 `format_sse` 的 event 字段一致） */
export const SKILL_UI_BOOTSTRAP = "SkillUiBootstrap" as const;
/** SSE 事件名：会话内交互卡片（左侧聊天流内渲染 SDUI 节点） */
export const SKILL_UI_CHAT_CARD = "SkillUiChatCard" as const;

/** 后端推送的 Bootstrap 载荷（`document` 为完整 SduiDocument JSON） */
export type SkillUiBootstrapPayload = {
  syntheticPath: string;
  document: unknown;
};

/** 前端归一化后的 Bootstrap 事件（供 SkillUiWrapper 竞争挂载） */
export type SkillUiBootstrapEvent = {
  id: string;
  syntheticPath: string;
  document: SduiDocument;
  receivedAt: number;
};

/** ChatCard SSE 载荷：在聊天流中插入/替换一张交互卡片 */
export type SkillUiChatCardPayload = {
  threadId?: string;
  /** 用于 replace 精准锁定 */
  cardId: string;
  mode?: "append" | "replace";
  /** 卡片 docId（默认：chat:<threadId>） */
  docId?: string;
  title?: string;
  /** 允许直接承载一个 SDUI 节点或一个完整 SduiDocument（宿主会兜底包一层 Stack） */
  node?: unknown;
  document?: unknown;
};

export type SkillUiChatCardEvent = {
  id: string;
  cardId: string;
  mode: "append" | "replace";
  docId: string;
  title?: string;
  /** 规范化后的节点树（root node） */
  node: SduiNode;
  receivedAt: number;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function nodeIdOf(node: unknown): string | null {
  if (!isRecord(node)) return null;
  const id = node.id;
  return typeof id === "string" && id.trim() ? id.trim() : null;
}

function indexNodesById(root: SduiNode): Map<string, SduiNode> {
  const map = new Map<string, SduiNode>();
  const walk = (n: SduiNode) => {
    const id = nodeIdOf(n);
    if (id) map.set(id, n);
    // children
    const ch = (n as { children?: SduiNode[] }).children;
    if (Array.isArray(ch)) ch.forEach(walk);
    // tabs
    if (n.type === "Tabs") {
      const tabs = (n as { tabs?: Array<{ children?: SduiNode[] }> }).tabs;
      if (Array.isArray(tabs)) {
        for (const t of tabs) {
          if (t && Array.isArray(t.children)) t.children.forEach(walk);
        }
      }
    }
  };
  walk(root);
  return map;
}

function indexSubtreeByIdIntoMap(root: SduiNode, map: Map<string, SduiNode>): void {
  const walk = (n: SduiNode) => {
    const id = nodeIdOf(n);
    if (id) map.set(id, n);
    const ch = (n as { children?: SduiNode[] }).children;
    if (Array.isArray(ch)) ch.forEach(walk);
    if (n.type === "Tabs") {
      const tabs = (n as { tabs?: Array<{ children?: SduiNode[] }> }).tabs;
      if (Array.isArray(tabs)) {
        for (const t of tabs) {
          if (t && Array.isArray(t.children)) t.children.forEach(walk);
        }
      }
    }
  };
  walk(root);
}

function deepMergeInPlace(target: Record<string, unknown>, patch: Record<string, unknown>): void {
  for (const [k, v] of Object.entries(patch)) {
    // Milestone-1 guardrails: do not patch structural fields.
    if (k === "children" || k === "tabs") continue;
    if (v === undefined) continue;
    const tv = target[k];
    if (isRecord(tv) && isRecord(v)) {
      deepMergeInPlace(tv, v);
    } else {
      target[k] = v;
    }
  }
}

/**
 * Apply an SDUI v3 patch to an existing parsed v2 document.
 *
 * Returns a new document object so React state updates propagate, while keeping
 * inner node object identities stable where possible (deep-merge in place).
 */
export function applySduiPatch(doc: SduiDocument, patch: SduiPatch): SduiDocument {
  // Shallow clone doc shell; mutate nodes in-place for stability.
  const next: SduiDocument = { ...doc, meta: doc.meta ? { ...doc.meta } : undefined };
  const byId = indexNodesById(next.root);

  for (const op of patch.ops || []) {
    const nodeId = op?.target?.nodeId;
    if (typeof nodeId !== "string" || !nodeId.trim()) continue;
    const id = nodeId.trim();

    const existing = byId.get(id);
    if (!existing) continue;

    if (op.op === "append") {
      const field = op?.target?.field;
      const isPartial = patch.isPartial === true;

      if (field === "children") {
        const container = existing as unknown as { children?: SduiNode[] };
        const prev = Array.isArray(container.children) ? container.children : [];
        const nextItems: SduiNode[] = [];

        if (Array.isArray(op.value)) {
          for (const item of op.value) {
            if (item && typeof item === "object" && (item as { type?: unknown }).type) {
              nextItems.push(item as SduiNode);
            }
          }
        } else if (op.value && typeof op.value === "object" && (op.value as { type?: unknown }).type) {
          nextItems.push(op.value as SduiNode);
        }

        if (nextItems.length) {
          if (isPartial) {
            for (const n of nextItems) {
              (n as unknown as { _partial?: boolean })._partial = true;
            }
          }
          container.children = prev.concat(nextItems);
          // Newly appended nodes should be addressable by later ops within the same patch.
          for (const n of nextItems) indexSubtreeByIdIntoMap(n, byId);
        }
      } else if (field === "rows") {
        // DataGrid.rows: opaque row records; no id indexing.
        const grid = existing as unknown as { type?: string; rows?: unknown[] };
        if (grid.type !== "DataGrid") continue;
        const prev = Array.isArray(grid.rows) ? grid.rows : [];
        const nextItems = Array.isArray(op.value) ? op.value : [op.value];
        const safeNext = nextItems.filter((x) => x !== undefined);
        if (safeNext.length) grid.rows = prev.concat(safeNext);
      } else if (field === "artifacts") {
        // ArtifactGrid.artifacts — 与 mission_control.add_artifact / build_append_op 对齐
        const grid = existing as unknown as { type?: string; artifacts?: SduiArtifactItem[] };
        if (grid.type !== "ArtifactGrid") continue;
        const prev = Array.isArray(grid.artifacts) ? grid.artifacts : [];
        const nextItems = Array.isArray(op.value) ? op.value : [op.value];
        const safeNext = nextItems.filter(
          (x): x is SduiArtifactItem =>
            x !== null &&
            typeof x === "object" &&
            typeof (x as SduiArtifactItem).id === "string" &&
            typeof (x as SduiArtifactItem).label === "string" &&
            typeof (x as SduiArtifactItem).path === "string",
        );
        if (safeNext.length) grid.artifacts = prev.concat(safeNext);
      }
      continue;
    }

    if (op.op === "remove") {
      // M1: structural deletion not supported; ignore safely.
      continue;
    }

    if (op.op === "replace") {
      // M1: replacing a node is structural and may unmount; allow only if type matches.
      if (op.value && (op.value as SduiNode).type === existing.type) {
        const t = existing as unknown as Record<string, unknown>;
        const v = op.value as unknown as Record<string, unknown>;
        // Keep id stable even if value omits it.
        const keepId = nodeIdOf(existing);
        for (const key of Object.keys(t)) delete t[key];
        for (const [k, val] of Object.entries(v)) t[k] = val;
        if (keepId && !nodeIdOf(t)) t.id = keepId;
      }
      continue;
    }

    if (op.op === "merge") {
      const patchValue = op.value as unknown;
      if (!isRecord(patchValue)) continue;
      // Enforce type match to avoid corrupting the tree.
      if (typeof patchValue.type !== "string" || patchValue.type !== existing.type) continue;
      deepMergeInPlace(existing as unknown as Record<string, unknown>, patchValue);
    }
  }

  return next;
}

export type SduiArtifactStatus = "ready" | "generating" | "error";
export type SduiArtifactKind = "docx" | "xlsx" | "pdf" | "html" | "json" | "md" | "png" | "other";

export type SduiArtifactItem = {
  id?: string;
  label?: string;
  path?: string;
  kind?: SduiArtifactKind;
  status?: SduiArtifactStatus;
};

export type SduiArtifactGridNode = {
  type: "ArtifactGrid";
  id?: string;
  title?: string;
  mode?: "input" | "output";
  artifacts: SduiArtifactItem[];
  flex?: number;
};

export type SduiGoldenMetricItem = {
  id?: string;
  label?: string;
  value?: number | string;
  color?: string;
};

export type SduiGoldenMetricsNode = SduiOptionalId & {
  type: "GoldenMetrics";
  metrics?: SduiGoldenMetricItem[];
};

export type SduiGuidanceAction = { label: string; verb: string; payload?: unknown };

export type SduiGuidanceCardNode = {
  type: "GuidanceCard";
  id?: string;
  context: string;
  actions: SduiGuidanceAction[];
  flex?: number;
};

export type SduiChoiceOption = { id: string; label: string };

export type SduiChoiceCardNode = {
  type: "ChoiceCard";
  id?: string;
  title: string;
  options: SduiChoiceOption[];
  /** 与 nextAction 一起用于 HITL 回传 module_action */
  moduleId?: string;
  nextAction?: string;
  flex?: number;
};

export type SduiNode =
  | SduiStackNode
  | SduiCardNode
  | SduiRowNode
  | SduiDividerNode
  | SduiTabsNode
  | SduiStepperNode
  | SduiSkeletonNode
  | SduiTextNode
  | SduiTextAreaNode
  | SduiMarkdownNode
  | SduiFilePickerNode
  | SduiBadgeNode
  | SduiStatisticNode
  | SduiKeyValueListNode
  | SduiTableNode
  | SduiDataGridNode
  | SduiButtonNode
  | SduiLinkNode
  | SduiChartPlaceholderNode
  | SduiGoldenMetricsNode
  | SduiDonutChartNode
  | SduiBarChartNode
  | SduiFileKindBadgeNode
  | SduiArtifactGridNode
  | SduiGuidanceCardNode
  | SduiChoiceCardNode
  | SduiStatisticRowNode
  | SduiGanttLaneNode
  | SduiGanttChartNode;

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
  /** 细分步骤：Hover Tooltip 展示 */
  detail?: SduiStepperDetailItem[];
};

/** 横向/纵向流程步骤条 */
export type SduiStepperNode = SduiOptionalId & {
  type: "Stepper";
  steps: SduiStepperStep[];
  /** 默认横向；纵向时适用于窄栏 */
  orientation?: "horizontal" | "vertical";
};

/** 流式 Bootstrap / 推测性渲染占位（封闭世界；无自由像素，仅用语义 variant） */
export type SduiSkeletonVariant = "text" | "rect" | "card" | "row";

export type SduiSkeletonNode = SduiOptionalId & {
  type: "Skeleton";
  variant?: SduiSkeletonVariant;
  /** variant=text 时的行数（1–8） */
  lines?: number;
  children?: SduiNode[];
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

export type SduiFilePickerNode = SduiOptionalId & {
  type: "FilePicker";
  /** 用于写入 meta.uiState.uploads.<purpose> */
  purpose: string;
  label?: string;
  helpText?: string;
  accept?: string;
  multiple?: boolean;
  moduleId?: string;
  nextAction?: string;
  /** workspace 相对目录，上传文件落盘为 ``<saveRelativeDir>/<净化后的原文件名>`` */
  saveRelativeDir?: string;
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

/** 横向指标行（JSON 中替代 Row+多个 Statistic，避免 Agent 拼错子节点） */
export type SduiStatisticRowItem = {
  title: string;
  value: string | number;
  color?: SduiSemanticColor;
};

export type SduiStatisticRowNode = SduiOptionalId & {
  type: "StatisticRow";
  items: SduiStatisticRowItem[];
};

export type SduiGanttBar = {
  label: string;
  /** 0–100，相对轨道起点 */
  startPct?: number;
  /** 0–100，宽度 */
  widthPct: number;
  color?: SduiSemanticColor;
};

export type SduiGanttLaneRow = {
  label: string;
  bars?: SduiGanttBar[];
};

export type SduiGanttLaneNode = SduiOptionalId & {
  type: "GanttLane";
  title?: string;
  caption?: string;
  lanes?: SduiGanttLaneRow[];
};

/** 与 {@link SduiGanttLaneNode} 同模型；常见 LLM 误写为 GanttChart，宿主统一映射到甘特轨 */
export type SduiGanttChartNode = SduiOptionalId & {
  type: "GanttChart";
  title?: string;
  caption?: string;
  lanes?: SduiGanttLaneRow[];
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
  /** v3 M1：点击扇区联动右栏预览（仅 open_preview / post_user_message） */
  action?: SduiAction;
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
  /** v3 M1：点击柱子联动右栏预览（仅 open_preview / post_user_message） */
  action?: SduiAction;
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
