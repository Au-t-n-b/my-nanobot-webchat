# Phase 3：Agentic Preview（智能降级与 Agent 洞察）设计稿

**日期**：2026-04-22  
**状态**：草案（待评审后进入实现计划）  
**依赖**：Phase 0 预览子系统（resolver / parsers / renderers）、Phase 2 ZIP、`skill.agent_task_execute` 混合子任务协议、`BaseRendererProps.onAction` 预留契约  

---

## Goal（目标）

当用户预览 **无法内联展示** 或 **体积/风险超出预览器能力** 的文件（如超大 `.log`、未知 `.dll/.exe`、加密/损坏 `.zip`）时，右侧不再止于「下载」卡片，而是提供 **「✨ 让 AI 深度诊断」** 入口：在 **受控、工作区内、工具白名单** 的前提下，拉起一次极短的 Agent 子任务，返回 **强 Schema** 的结构化洞察，并在预览区以仪表盘形式呈现。

---

## Non-goals（非目标）

- 不在预览器内实现「完整数据库客户端」式分析（与 Phase 1 克制一致）。
- 不默认自动触发 Agent（必须用户显式点击 CTA，避免费用与隐私风险）。
- Phase 3.0 **不要求** 引入重量级编码探测库（如全量 `iconv`）；文本乱码继续以「下载原文件」为主提示。
- 不把 Agent 结果耦合进 **`resolvePreview(path)`**：该函数必须保持 **纯函数**；洞察结果走 **独立状态通道**（见下文「架构边界」）。

---

## 核心业务场景

| 场景 | 当前行为 | Phase 3 行为 |
|------|----------|--------------|
| 超大 `.log`（如 50MB） | 可能走文本/降级或失败 | CTA → 子任务只读 tail/关键词 → `InsightRenderer` |
| `.dll` / `.exe` / 未知二进制 | `BinaryRenderer` 仅下载 | CTA → 元数据/魔数/风险等级摘要 |
| 加密或无法解析的 `.zip` | 错误/下载 | CTA → 列出可读信息 + 建议 |

---

## 架构边界（与 Phase 0 铁律对齐）

### 1) `resolvePreview` 保持纯函数

**禁止**：在 `previewResolver.ts` 内根据「是否已有洞察」动态改变 kind（会依赖非 path 的全局/异步状态，破坏可测试性与同 path 同输出）。

**推荐**：

- **解析层**：仍只由 `path` → `PreviewResolution`（含 kind / fetch）。
- **洞察层**：在 `PreviewFileViewer` / `PreviewPanel` 壳层维护 `insight` 状态机：`idle | requesting | ready | error`，与 parser 输出 **正交**。
- **呈现层**：当 `insight.status === "ready"` 时，**优先**渲染 `InsightRenderer`（或 split：上半原预览/降级，下半洞察面板），而不是改 resolver。

### 2) `onAction` 上升路径

`BaseRendererProps` 已预留 `onAction?: (action: string, payload: unknown) => void`。

- **Renderer**（如升级后的 `BinaryRenderer` / 新增 `FallbackRenderer`）：只 `onAction("REQUEST_AGENT_INSIGHT", { path, reason, ... })`。
- **PreviewFileViewer / PreviewPanel**：默认不处理则忽略；若父组件传入 `onPreviewInsightRequest`，则向上抛出。
- **Workbench**：注入实现：组装 `buildSkillAgentTaskExecuteEnvelope(...)` 所需字段（`threadId`、`skillRunId`、`skillName`、白名单工具等），通过既有 **SDUI / Agent 消息通道** 发往 bridge（与现有 Hybrid 一致）。

> 说明：具体「发到哪条 API / 是否复用 `postToAgent`」以 Workbench 现有能力为准；Phase 3 实现前在计划中锁定唯一入口，避免双通道。

---

## 前端：触发与 UI

### 1) 升级降级卡片（插入点）

当前二进制降级为 `frontend/components/preview/renderers/BinaryRenderer.tsx`（仅下载）。Phase 3 可二选一：

- **A（推荐）**：扩展 `BinaryRenderer`，增加 CTA + `onAction`（保持单组件职责：降级 + CTA）。
- **B**：抽 `FallbackRenderer.tsx`，把「不支持 / 过大 / 加密」统一收口，再让 `PreviewFileViewer` 路由到它。

CTA 文案示例：「该文件过大或无法预览，是否调用认知引擎进行结构化诊断？」

### 2) 状态机（壳层）

在 `PreviewFileViewer`（或仅 `PreviewPanel` 包一层）增加：

```text
insight: idle → requesting → ready | error
```

- `requesting`：展示「Agent 呼吸态」占位（与现有 hybrid 提示可并存）。
- `ready`：解析 JSON 为 `FileInsightReport`，渲染 `InsightRenderer`。
- `error`：展示错误 + 仍保留下载。

### 3) `InsightRenderer.tsx`（新建）

纯展示：接收 `report: FileInsightReport`，展示风险等级、摘要、`extracted_snippets`、下一步建议。不 fetch、不调 Agent。

---

## 后端：FileInsight 子任务契约

复用 **`skill.agent_task_execute`**，不新增平行「神秘协议」，除非后续证明必须拆分。

### Goal 模板（示例）

> 仅分析工作区内路径 `{path}`：在不下载到临时目录的前提下，通过允许的工具读取有限字节/尾部行数，输出符合 `FileInsightReport` 的 JSON。

### 工具白名单（建议）

- `read_file`（必须带 offset/limit 或平台支持的「仅读头/尾」语义；若无则严格限制 max 字符）
- 可选：`extract_doc_text` 仅当扩展名为 doc/docx 且策略允许
- **禁止**：任意 shell、网络、写文件

### 强 Schema（Pydantic，后端）

```python
from typing import Literal
from pydantic import BaseModel, Field

class FileInsightReport(BaseModel):
    file_type_guess: str = Field(..., description="类型猜测，如 PE / UTF-8 text / gzip")
    summary: str
    risk_level: Literal["safe", "warning", "danger"]
    extracted_snippets: list[str] = Field(default_factory=list, max_length=20)
    next_action_suggestion: str
```

返回方式（二选一，实现前锁定）：

1. **子任务结束 JSON** 写入某 SSE 事件 payload（与现有 hybrid 结果路径一致），前端监听同一 thread 解析。
2. **`dashboard.patch`** 写入专用节点（需 SDUI 节点 id 约定）；预览侧订阅 patch 流（若 Workbench 已暴露则复用）。

---

## 安全与合规

- **显式同意**：仅 CTA 触发。
- **数据最小化**：snippet 条数与单条长度上限；日志类默认 tail。
- **路径**：仅允许 `workspace/...` 相对路径，与现有 `/api/file` 一致。
- **风险展示**：`danger` 不等于「恶意已证实」，文案需避免法律误导。

---

## 验收标准（Phase 3.0）

- 对至少一类「仅 Binary 降级」的文件，用户点击 CTA 后能看到 **进行中** → **结构化报告** 或 **明确错误**。
- 全程不破坏 `resolvePreview` 纯函数与现有 parser/renderer 无副作用契约。
- 不自动发起子任务；失败时仍可下载。

---

## 与现有代码的映射

- 子任务信封：`frontend/lib/skillHybridProtocol.ts` → `buildSkillAgentTaskExecuteEnvelope`
- 混合提示：`hybridSubtaskHintFromTaskStatus`（可与预览区「呼吸态」并存）
- 降级 UI：`BinaryRenderer`（当前扩展主入口）

---

## 开放问题（实现计划前需拍板）

1. **Insight 结果回传**：优先走「SSE 子任务结果」还是 `dashboard.patch`？（建议优先与 hybrid 现有回传路径一致。）
2. **Workbench 注入点**：`PreviewPanel` 是否新增 `onPreviewInsightRequest` prop，还是复用 `onFillInput`/`postToAgent` 的既有回调？
3. **超大文件**：是否在 CTA 前就做 `HEAD`/`content-length` 拦截，避免用户误点？
