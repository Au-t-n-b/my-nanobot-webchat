# Phase 3：Agentic Preview（智能降级与 Agent 洞察）设计稿

**日期**：2026-04-22  
**状态**：**已裁决（Architecture Locked）** — 开放问题已收口；实施见 `docs/superpowers/plans/2026-04-22-agentic-preview.md`  
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

- **解析层**：仍只由 `path` → `PreviewResolution`（含 kind / fetch / url；**可选** `meta` 字段见下文「文件大小元数据」）。
- **洞察层**：在 `PreviewFileViewer`（壳层）维护 `insight` 状态机：`idle | requesting | ready | error`，与 parser 输出 **正交**。
- **呈现层**：当 `insight.status === "ready"` 时，**优先**渲染 `InsightRenderer`（或 split：上半原预览/降级，下半洞察面板），而不是改 resolver。

### 2) Workbench 注入：专属 RPC 契约 `onPreviewInsightRequest`

**裁决**：不复用 `onFillInput` / `postToAgent` 的「聊天流」语义；预览洞察需要 **明确的 RPC 语义**。

- 在 **`PreviewFileViewerProps`** 增加：  
  `onPreviewInsightRequest?: (path: string) => Promise<FileInsightReport>`
- 外层 **Workbench** 负责：组装 `skill.agent_task_execute` 信封、发起请求、订阅 SSE、在特定 `taskId` 完成时 **resolve Promise**；`PreviewFileViewer` 内只 `await` 并驱动状态机，便于 Storybook Mock。

`BaseRendererProps.onAction` 仍可作为 renderer 内部向壳层冒泡的 **实现细节**（例如 `"REQUEST_AGENT_INSIGHT"`），但 **对外契约** 以 `onPreviewInsightRequest` 为准。

### 3) 文件大小元数据（`PreviewResolution.meta`）

**裁决**：超大文件 CTA 拦截 **复用** 已知大小信息，**禁止**为「能否点 CTA」再单独打一圈预检请求。

- 在 **`PreviewResolution`** 上增加可选字段，例如 `meta?: { sizeBytes?: number }`。
- **`resolvePreview(path)` 仍不发起网络**、也不读取异步状态；`meta` **不由** resolver 同步填充。
- **壳层合并**：凡已通过 `/api/file` 拉取或解析的路径（parser 首包已读到 `Content-Length`），将 `sizeBytes` 写入 **派生** 的 `resolutionForUi` 再传给 renderer；对 **`fetch === "none"` 且需展示 CTA 的二进制路径**，允许壳层做 **与下载同源的一次** `HEAD`（或等价元数据）以填充 `meta` —— 这与「不为 CTA 单独再加一次预检」一致：要么复用已有响应头，要么二进制路径仅此一次元数据请求。

**产品规则**：若 `meta.sizeBytes > 500 * 1024 * 1024`，CTA **disabled**，文案：「文件极其庞大，为确保性能，AI 诊断暂不可用。」

---

## 前端：触发与 UI

### 1) 升级降级卡片（插入点）

当前二进制降级为 `frontend/components/preview/renderers/BinaryRenderer.tsx`（仅下载）。Phase 3 可二选一：

- **A（推荐）**：扩展 `BinaryRenderer`，增加 CTA + 与壳层传入的回调绑定（保持单组件职责：降级 + CTA）。
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

> 仅分析工作区内路径 `{path}`：通过允许的工具读取 **严格上限** 的字节/行，输出 **唯一** 一段符合 `FileInsightReport` 的 JSON（不要 markdown 围栏）。

### 工具白名单（已裁决 + 避坑）

- **禁止**向 File Insight 子任务暴露无约束的 `read_file` 作为主力工具（即使现有 `ReadFileTool` 有分页，仍可能被宽 `limit` 或大行撑爆进程 / 上下文）。
- **必须**提供签名层即卡死读取量的工具，例如：  
  - `read_file_head(path, lines=100)`  
  - `read_file_tail(path, lines=100)`  
  - `read_hex_dump(path, bytes=256)`  
- 可保留 `list_dir` 等低风险只读工具；其它工具按场景收紧。

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

### Insight 结果回传（已裁决）

**走 SSE 专用子任务结果通道；坚决不走 `dashboard.patch`。**

- **理由**：预览洞察是 **临时态（Ephemeral）**；写入 SDUI 状态树会导致膨胀并破坏模块数据隔离。
- **做法**：子任务完成后，由后端经 **与现有 chat SSE 同流** 的事件推送结构化 payload（实现层事件名建议与前端枚举对齐，例如 **`SkillAgentTaskResult`**；概念上即「`skill_agent_task_result` 类通道」）。前端按 **`taskId`** 过滤，在 **`onPreviewInsightRequest` 的 Promise** 中 resolve；`PreviewFileViewer` 仅更新局部 `insight` state。
- **与现状对齐**：当前 `_emit_skill_agent_task_execute` 在存在 `syntheticPath` 时会把摘要 **merge 进 dashboard** —— **File Insight 模式必须跳过该分支**，仅发 SSE 结果事件。

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
- Insight 结果 **不**经 `SkillUiDataPatch` / `dashboard.patch` 进入主干 SDUI 树。

---

## 与现有代码的映射

- 子任务信封：`frontend/lib/skillHybridProtocol.ts` → `buildSkillAgentTaskExecuteEnvelope`
- 混合提示：`hybridSubtaskHintFromTaskStatus`（可与预览区「呼吸态」并存）
- 降级 UI：`BinaryRenderer`（当前扩展主入口）
- Hybrid 执行与 patch：`nanobot/web/skill_runtime_bridge.py` → `_emit_skill_agent_task_execute`
- SSE 写出：`nanobot/web/routes.py`（`TaskStatusUpdate` 等同路径旁新增结果事件绑定）

---

## 架构师裁决摘要（The Rulings）

| # | 主题 | 裁决 |
|---|------|------|
| 1 | Insight 回传 | **SSE 子任务结果通道**；**禁止** `dashboard.patch` 持久化 JSON。 |
| 2 | Workbench 注入 | 新增 **`onPreviewInsightRequest?: (path: string) => Promise<FileInsightReport>`**（`PreviewFileViewerProps`）；**禁止**复用 `onFillInput` / `postToAgent` 作为对外契约。 |
| 3 | 超大文件 CTA | 使用 **`PreviewResolution.meta.sizeBytes`**（壳层填充）；`> 500MB` 禁用 CTA 并固定中文提示；**禁止**为 CTA 单独再加无意义的二次预检。 |

---

## 后端避坑锦囊（Agent 也会被大文件撑爆）

在实现工具层时，**不要**把原生大容量 `read_file` 交给 Insight Agent。必须在 **工具签名与实现** 上限制读取量，迫使模型「管中窥豹」并完成 `file_type_guess` —— 见上文 **工具白名单（已裁决 + 避坑）**。
