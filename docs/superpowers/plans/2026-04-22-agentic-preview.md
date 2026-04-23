# Phase 3 Agentic Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在预览壳层实现「AI 深度诊断」：用户点击 CTA 后发起受控 `skill.agent_task_execute` 子任务，通过 **SSE 专用结果事件** 拿回 `FileInsightReport` JSON，在 `PreviewFileViewer` 的 **正交状态机** 中展示；**绝不**把洞察写入 `dashboard.patch`；后端仅为洞察配置 ** capped 读文件工具**，避免 Agent OOM。

**Architecture:** `resolvePreview` 保持纯函数；`PreviewResolution.meta.sizeBytes` 仅由壳层/解析链已得信息合并；`PreviewFileViewerProps.onPreviewInsightRequest(path) => Promise<FileInsightReport>` 由 Workbench 实现（信封 + SSE 订阅 + taskId 对齐）；后端 `_emit_skill_agent_task_execute` 在 `resultDelivery: "sse"` 时 **跳过** `_emit_dashboard_patch`，并 `emit_skill_agent_task_result`（SSE 事件名 **`SkillAgentTaskResult`**，与 `TaskStatusUpdate` 同流绑定方式）；`run_hybrid_agent_subtask` 增加 JSON 输出模式与 capped 工具注册。

**Tech Stack:** Next.js/React、TypeScript、现有 preview 子系统、Python aiohttp SSE、`pydantic`、`skill_runtime_bridge` / `hybrid_agent_subtask`

**规格锁定:** `docs/superpowers/specs/2026-04-22-agentic-preview-design.md`

---

## File Structure（将创建/修改的文件）

**Create:**

- `d:\code\nanobot\frontend\components\preview\renderers\InsightRenderer.tsx`（纯展示 `FileInsightReport`）
- （可选）`d:\code\nanobot\frontend\lib\fileInsightTypes.ts`（若不宜全部塞进 `previewTypes.ts`）

**Modify:**

- `d:\code\nanobot\frontend\components\preview\previewTypes.ts` — `PreviewResolution.meta`；`FileInsightReport` 类型；必要时扩展 `BaseRendererProps`
- `d:\code\nanobot\frontend\components\preview\PreviewFileViewer.tsx` — `insight` 状态机、`onPreviewInsightRequest`、向 `BinaryRenderer` 等注入回调与 `resolutionForUi`
- `d:\code\nanobot\frontend\components\preview\renderers\BinaryRenderer.tsx` — CTA、`meta.sizeBytes` 门槛（500MB）、禁用态文案
- `d:\code\nanobot\frontend\components\preview\PreviewPanel.tsx` — 透传 `onPreviewInsightRequest`
- `d:\code\nanobot\frontend\components\preview\previewParsers.ts` — 在已有 `fetch()` 路径把 `Content-Length` 可靠时回传给壳层（例如 parser 返回 `sourceSizeBytes` 或在统一 helper 中解析）
- `d:\code\nanobot\frontend\lib\skillHybridProtocol.ts` — `SkillAgentTaskExecutePayload`：`resultDelivery?: "sse"` 时 `syntheticPath`/`docId` 可选；文档注释与 `buildSkillAgentTaskExecuteEnvelope` 行为一致
- `d:\code\nanobot\frontend\hooks\useAgentChat.ts` — 解析 SSE 事件 `SkillAgentTaskResult`，暴露给 Workbench（见 Task 7 选定的一种订阅机制）
- `d:\code\nanobot\frontend\components\workbench\WorkbenchContent.tsx`（或当前挂载 `PreviewPanel` 的父组件）— 实现 `onPreviewInsightRequest`
- `d:\code\nanobot\nanobot\agent\loop.py` — `ContextVar` + `emit_skill_agent_task_result_event` + `set_*` / `reset_*`（对称于 `emit_task_status_event`）
- `d:\code\nanobot\nanobot\agent\*.py`（若 Agent 类集中管理 emitters）— 绑定新 emitter 存根
- `d:\code\nanobot\nanobot\web\routes.py` — fastlane 与 `/api/chat` 流内注册 `SkillAgentTaskResult` 写出回调
- `d:\code\nanobot\nanobot\web\skill_runtime_bridge.py` — `_emit_skill_agent_task_execute`：SSE 结果、`resultDelivery` 分支、禁止 patch；默认行为保持工勘兼容
- `d:\code\nanobot\nanobot\web\hybrid_agent_subtask.py` — 注册 `read_file_head` / `read_file_tail` / `read_hex_dump`；`output_mode: "file_insight_json"` 时切换 system prompt 要求 **仅输出 JSON**
- `d:\code\nanobot\nanobot\agent\tools\filesystem.py`（或新模块）— 三个 capped 工具类
- `d:\code\nanobot\nanobot\web\` 下新增或现有 Pydantic 模型文件 — `FileInsightReport` 校验 + 子任务结束后解析 hybrid 文本

**Test:**

- `d:\code\nanobot\tests\web\test_skill_agent_task_execute.py` — 新增用例：`resultDelivery=sse` 时不调用 patch mock、会触发结果 emitter
- `d:\code\nanobot\tests\web\` 或 `tests/agent\` — capped 工具硬限制单测

**Verify:**

- `cd d:\code\nanobot\frontend && npx tsc --noEmit`
- `cd d:\code\nanobot && python -m pytest tests/web/test_skill_agent_task_execute.py -q`

---

### Task 1: 前端类型 — `FileInsightReport` 与 `PreviewResolution.meta`

**Files:**

- Modify: `d:\code\nanobot\frontend\components\preview\previewTypes.ts`

- [ ] **Step 1: 扩展 `PreviewResolution`**

```ts
import type { PreviewKind } from "@/lib/previewKind";

export type PreviewFileMeta = {
  /** 字节数；未知时可省略 */
  sizeBytes?: number;
};

export type PreviewResolution = {
  path: string;
  kind: PreviewKind;
  url?: string;
  fetch: PreviewFetchMode;
  meta?: PreviewFileMeta;
};
```

- [ ] **Step 2: 增加 `FileInsightReport`（与后端 Pydantic 字段对齐）**

```ts
export type FileInsightRiskLevel = "safe" | "warning" | "danger";

export type FileInsightReport = {
  file_type_guess: string;
  summary: string;
  risk_level: FileInsightRiskLevel;
  extracted_snippets: string[];
  next_action_suggestion: string;
};
```

- [ ] **Step 3: 运行 `npx tsc --noEmit`**

Expected: PASS（若 `PreviewResolution` 引用方需同步，本步一并修完）。

- [ ] **Step 4: Commit**

```bash
git add frontend/components/preview/previewTypes.ts
git commit -m "feat(preview): FileInsightReport 与 PreviewResolution.meta 类型"
```

---

### Task 2: 协议载荷 — `resultDelivery: "sse"` 与可选 patch 字段

**Files:**

- Modify: `d:\code\nanobot\frontend\lib\skillHybridProtocol.ts`

- [ ] **Step 1: 扩展 `SkillAgentTaskExecutePayload`**

在现有字段基础上增加：

```ts
export type SkillAgentTaskResultDelivery = "dashboard" | "sse";

export type SkillAgentTaskExecutePayload = {
  taskId: string;
  parentRequestId?: string;
  skillName?: string;
  stepId: string;
  goal: string;
  allowedTools?: string[];
  maxIterations?: number;
  resultSchema?: { type: string; [key: string]: unknown };
  /** 默认 dashboard：与现网工勘一致。preview insight 必须用 sse。 */
  resultDelivery?: SkillAgentTaskResultDelivery;
  /** resultDelivery === "dashboard" 时必填；sse 模式下省略 */
  syntheticPath?: string;
  docId?: string;
  summaryNodeId?: string;
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/skillHybridProtocol.ts
git commit -m "feat(hybrid): skill.agent_task_execute 支持 SSE 结果投递"
```

---

### Task 3: 后端 — capped 读文件工具

**Files:**

- Modify: `d:\code\nanobot\nanobot\agent\tools\filesystem.py`（或 `nanobot/agent/tools/preview_insight_read.py` 新文件并在 registry 构建处引用）

- [ ] **Step 1: 实现三个 Tool**

约束示例（实现时可微调常量，但必须写死上限并在 `parameters` 的 `maximum` 中体现）：

- `read_file_head`：`lines` 默认 100，最大 200；只读 UTF-8 文本行首（二进制可读则按 errors=replace 或明确拒绝非文本）。
- `read_file_tail`：同上，从 EOF 向前读。
- `read_hex_dump`：`bytes` 默认 256，最大 512；返回十六进制 + ASCII 列（与 `xxd` 风格类似即可）。

- [ ] **Step 2: 单测**

新增 `tests/.../test_preview_insight_tools.py`：对超过上限的入参 clamp 或拒绝（二选一行文锁死并在测试中断言）。

- [ ] **Step 3: Commit**

```bash
git add nanobot/agent/tools/ tests/
git commit -m "feat(tools): preview insight 专用 capped 读文件工具"
```

---

### Task 4: 后端 — `hybrid_agent_subtask` 支持 `file_insight_json`

**Files:**

- Modify: `d:\code\nanobot\nanobot\web\hybrid_agent_subtask.py`

- [ ] **Step 1: 为 `_build_tool_registry` 注册新工具名**

当 `allowed_tools` 包含 `read_file_head` / `read_file_tail` / `read_hex_dump` 时注册对应类；**Insight 配置禁止把 `read_file` 加入白名单**（由调用方 `skill_runtime_bridge` 在 preview 模式强制覆盖）。

- [ ] **Step 2: `run_hybrid_agent_subtask(..., output_mode: str = "summary_zh")`**

当 `output_mode == "file_insight_json"`：

- system prompt 改为要求：**最终 assistant 消息必须为单行合法 JSON**，匹配 `FileInsightReport` 字段；禁止 markdown 围栏；仍须通过工具取事实。

- [ ] **Step 3: pytest**

扩展或新增测试：mock provider 返回无 tool 调用的最终 JSON，`run_hybrid_agent_subtask` 返回 `ok` 与 `text` 为 JSON 字符串。

- [ ] **Step 4: Commit**

```bash
git add nanobot/web/hybrid_agent_subtask.py tests/
git commit -m "feat(hybrid): file_insight_json 输出模式与 capped 工具注册"
```

---

### Task 5: 后端 — SSE `SkillAgentTaskResult` 发射链

**Files:**

- Modify: `d:\code\nanobot\nanobot\agent\loop.py`
- Modify: `d:\code\nanobot\nanobot\web\routes.py`（两处 emitter 绑定 + `finally` reset）
- （若需要）Agent 包装类：与 `set_task_status_emitter` 对称增加 setter

- [ ] **Step 1: 在 `loop.py` 增加 ContextVar 与 emit 函数**

模式复制 `emit_task_status_event`：

```python
_SKILL_AGENT_TASK_RESULT_EMITTER: ContextVar[Any | None] = ContextVar(
    "skill_agent_task_result_emitter", default=None
)

async def emit_skill_agent_task_result_event(payload: dict[str, Any]) -> None:
    cb = _SKILL_AGENT_TASK_RESULT_EMITTER.get()
    if cb is None:
        logger.debug("skill_agent_task_result_emit_skipped | reason=no_sse_emitter")
        return
    await cb(payload)
```

并提供 `set_skill_agent_task_result_emitter` / `reset_*`（命名与项目现有风格一致）。

- [ ] **Step 2: `routes.py` 注册 SSE**

在 `emit_task_status` 旁增加：

```python
async def emit_skill_agent_task_result(payload: dict[str, Any]) -> None:
    await safe_write("SkillAgentTaskResult", payload)
```

并把 token 压栈与 `finally` 释放补齐（fastlane 与主 chat 两条路径都要绑）。

- [ ] **Step 3: Commit**

```bash
git add nanobot/agent/loop.py nanobot/web/routes.py
git commit -m "feat(sse): SkillAgentTaskResult 事件管道"
```

---

### Task 6: 后端 — `skill_runtime_bridge` 集成 SSE 与跳过 dashboard patch

**Files:**

- Modify: `d:\code\nanobot\nanobot\web\skill_runtime_bridge.py`

- [ ] **Step 1: 读取 `resultDelivery`**

```python
result_delivery = str(payload.get("resultDelivery") or "dashboard").strip().lower()
```

- [ ] **Step 2: 调用 `run_hybrid_agent_subtask` 时传入 `output_mode`**

- `result_delivery == "sse"` → `output_mode="file_insight_json"`
- 否则保持现有中文摘要模式

- [ ] **Step 3: `allowed_tools` 强制**

当 `result_delivery == "sse"` 且识别为 preview insight（可用 `stepId == "preview.file_insight"` 或 payload 显式 `kind: "preview_file_insight"`）：

```python
allowed_tools = ["read_file_head", "read_file_tail", "read_hex_dump", "list_dir"]
```

- [ ] **Step 4: 子任务结束后**

1. 若 `result_delivery == "sse"`：解析 `hybrid["text"]` 为 JSON → `FileInsightReport`（pydantic）；调用 `await emit_skill_agent_task_result_event({...})`，payload 至少包含：`threadId`（从 envelope）、`taskId`、`ok`、`report` 或 `error`。  
2. **不调用** `_emit_dashboard_patch`。  
3. 若 `result_delivery == "dashboard"`：保持现有 `syntheticPath` + patch 逻辑。

- [ ] **Step 5: 更新 `tests/web/test_skill_agent_task_execute.py`**

Mock `emit_skill_agent_task_result_event` 与 patch emitter；断言 sse 路径下 patch 未触发。

- [ ] **Step 6: Commit**

```bash
git add nanobot/web/skill_runtime_bridge.py tests/web/test_skill_agent_task_execute.py
git commit -m "feat(skill): preview file insight 走 SSE 且跳过 dashboard patch"
```

---

### Task 7: 前端 — 消费 `SkillAgentTaskResult` 并完成 `onPreviewInsightRequest`

**Files:**

- Modify: `d:\code\nanobot\frontend\hooks\useAgentChat.ts`
- Modify: `d:\code\nanobot\frontend\components\workbench\WorkbenchContent.tsx`（路径以仓库实际为准，可用 grep `PreviewPanel` 定位）

- [ ] **Step 1: 在 SSE 分发处增加分支**

```ts
} else if (event === "SkillAgentTaskResult") {
  const payload = data as { taskId?: string; ok?: boolean; report?: FileInsightReport; error?: string };
  // 调用 module 级回调或写入 zustand/Ref：见 Step 2
}
```

- [ ] **Step 2: Workbench 实现 `onPreviewInsightRequest`**

伪代码（需与现有 `postMessage` / `fetch` chat 流对齐）：

```ts
async function onPreviewInsightRequest(path: string): Promise<FileInsightReport> {
  const taskId = `preview-insight-${crypto.randomUUID()}`;
  const pending = new Promise<FileInsightReport>((resolve, reject) => {
    registerSkillAgentTaskListener(taskId, (payload) => {
      if (payload.ok && payload.report) resolve(payload.report);
      else reject(new Error(payload.error || "insight_failed"));
    });
  });
  await sendSkillRuntimeEvent(buildSkillAgentTaskExecuteEnvelope({
    threadId,
    skillName,
    skillRunId,
    payload: {
      taskId,
      stepId: "preview.file_insight",
      goal: buildFileInsightGoal(path),
      resultDelivery: "sse",
      allowedTools: ["read_file_head", "read_file_tail", "read_hex_dump", "list_dir"],
      maxIterations: 8,
      resultSchema: { type: "FileInsightReport" },
    },
  }));
  return await pending;
}
```

`registerSkillAgentTaskListener` 的具体实现优先复用 **同一 chat SSE 连接** 上的 ref Map（避免第二条 WebSocket）。

- [ ] **Step 3: Commit**

```bash
git add frontend/hooks/useAgentChat.ts frontend/components/workbench/
git commit -m "feat(workbench): preview insight RPC 与 SkillAgentTaskResult 订阅"
```

---

### Task 8: 前端 — `PreviewFileViewer` 状态机 + `BinaryRenderer` CTA

**Files:**

- Modify: `d:\code\nanobot\frontend\components\preview\PreviewFileViewer.tsx`
- Modify: `d:\code\nanobot\frontend\components\preview\renderers\BinaryRenderer.tsx`
- Create: `d:\code\nanobot\frontend\components\preview\renderers\InsightRenderer.tsx`
- Modify: `d:\code\nanobot\frontend\components\preview\PreviewPanel.tsx`

- [ ] **Step 1: `PreviewFileViewerProps`**

```ts
export type PreviewFileViewerProps = {
  path: string;
  onOpenPath: (path: string) => void;
  activeSkillName?: string | null;
  onFillInput?: (text: string) => void;
  initialBuffer?: ArrayBuffer;
  onClosePanel?: () => void;
  onPreviewInsightRequest?: (path: string) => Promise<FileInsightReport>;
};
```

- [ ] **Step 2: `insight` 状态与 UI**

`useState` + `useCallback`：`requestInsight` 内 `setInsight({ status: "requesting" })`，`try { const r = await onPreviewInsightRequest?.(path) }`。

- [ ] **Step 3: `BinaryRenderer`**

Props 扩展：`sizeBytes?: number`、`insightDisabledReason?: string`、`onRequestInsight?: () => void`、`insightStatus?: "idle" | "requesting" | "ready" | "error"`。

当 `sizeBytes > 500 * 1024 * 1024`：按钮 `disabled`，展示裁决指定中文文案。

- [ ] **Step 4: `InsightRenderer`**

仅展示 `report`，无 IO。

- [ ] **Step 5: `npx tsc --noEmit`**

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add frontend/components/preview/
git commit -m "feat(preview): Agent 洞察壳层状态机与 BinaryRenderer CTA"
```

---

### Task 9: 壳层合并 `meta.sizeBytes`（parser 与 binary HEAD）

**Files:**

- Modify: `d:\code\nanobot\frontend\components\preview\previewParsers.ts`
- Modify: `d:\code\nanobot\frontend\components\preview\PreviewFileViewer.tsx`

- [ ] **Step 1: 对已有 `fetch` 的 parser**

在读取 `response.headers.get("content-length")` 成功时，通过返回值或 `PreviewFileViewer` 内 `setResolvedMeta({ sizeBytes })` 合并进传给子组件的 `resolution`。

- [ ] **Step 2: 对 `kind === "binary"` 早返回路径**

`useEffect` 发起单次 `HEAD` 到 `resolution.url`（credentials 与现有 `api/file` 一致），仅填充 `meta.sizeBytes`，失败则保持 `meta` 未定义（CTA 仍可启用或按产品选择默认允许 —— 规格未禁用时保持可用）。

- [ ] **Step 3: Commit**

```bash
git add frontend/components/preview/previewParsers.ts frontend/components/preview/PreviewFileViewer.tsx
git commit -m "feat(preview): 合并 Content-Length 与 binary HEAD 元数据"
```

---

### Task 10: 文档与收尾

- [ ] **确认** `docs/superpowers/specs/2026-04-22-agentic-preview-design.md` 与实现一致。
- [ ] **全量验证**

Run:

```bash
cd d:\code\nanobot\frontend && npx tsc --noEmit
cd d:\code\nanobot && python -m pytest tests/web -q
```

Expected: 全部 PASS。

- [ ] **Commit**

```bash
git add docs/superpowers/
git commit -m "docs(preview): Phase 3 Agentic Preview 实施收尾"
```
