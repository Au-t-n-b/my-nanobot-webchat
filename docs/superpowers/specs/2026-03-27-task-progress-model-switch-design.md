# 任务进度追踪与模型切换设计规格书

**状态:** Draft  
**日期:** 2026-03-27  
**范围:** `nanobot/nanobot/web/routes.py`、`frontend/hooks/useAgentChat.ts`、`frontend/app/page.tsx`、`frontend/components/ModelSelector.tsx`、`frontend/components/TaskProgressBar.tsx`

---

## 1. 目标与边界

### 1.1 目标

- 新增 `GET /api/task-status`，为前端任务看板提供统一读取接口。
- 在 `POST /api/chat` 支持可选 `model_name`，允许前端按“本次请求”动态切模型。
- 前端新增模型选择器与任务看板，并与后端接口联调完成。

### 1.2 已确认决策

- `model_name` 采用 **请求级生效**（仅当前 run）。
- 不引入会话级或全局级模型状态写入。
- `task_progress.json` 不存在时返回默认空模板（`200`），减少前端首屏异常处理成本。

### 1.3 非目标（本轮不做）

- 不改动现有并发锁生命周期逻辑（409 相关修复保持不变）。
- 不在本轮引入模型白名单后端硬校验（可后续增量）。
- 不修改既有 SSE 事件结构（仅扩展请求参数）。

---

## 2. 后端 API 设计

### 2.1 `GET /api/task-status`

- **路由:** `/api/task-status`
- **读取位置:** `workspace/task_progress.json`（workspace 由现有 `_agui_workspace_root(config)` 决定）
- **响应策略:**
  - 文件存在且 JSON 合法：`200` + 文件 JSON
  - 文件不存在：`200` + 默认模板
  - 文件存在但 JSON 非法：`500` + `{"detail":"..."}`
- **错误体约定:** 与现有路由风格对齐，统一使用 `{"detail":"<message>"}`。

默认模板（建议契约）：

```json
{
  "updatedAt": null,
  "overall": { "doneCount": 0, "totalCount": 6 },
  "modules": [
    { "id": "m1", "name": "需求分析", "status": "pending", "steps": [] },
    { "id": "m2", "name": "方案设计", "status": "pending", "steps": [] },
    { "id": "m3", "name": "后端实现", "status": "pending", "steps": [] },
    { "id": "m4", "name": "前端实现", "status": "pending", "steps": [] },
    { "id": "m5", "name": "联调验证", "status": "pending", "steps": [] },
    { "id": "m6", "name": "回归发布", "status": "pending", "steps": [] }
  ]
}
```

模板约束：

- `overall.totalCount === modules.length`
- `overall.doneCount === modules.filter(m => m.status === "completed").length`
- `status` 枚举值为 `"pending" | "running" | "completed"`
- `steps` 元素结构统一为 `{ id: string, name: string, done: boolean }`

### 2.2 `POST /api/chat` 扩展参数

- **新增可选字段:** `model_name?: string`
- **解析规则:**
  - 缺失/空字符串：使用后端当前默认模型（以运行时配置为准，不在规格写死具体型号）
  - 非空字符串：作为本次请求模型传入底层调用
- **作用域:** 仅本次请求，不修改全局 `agent.model` 持久状态。

### 2.3 传递到 Agent/LLM 的方式

- 明确透传链路：`process_direct(..., model_name?: string)` → `_process_message(..., model_name?: string)` → `_run_agent_loop(..., model_name?: string)` → provider 调用。
- provider 调用模型选择优先级：`model_name`（本次请求） > 运行时默认模型。
- `RunStarted.model` 必须回显“本次 provider 实际使用模型名”，禁止仅回显静态配置字段。

### 2.4 错误与兼容性

- `model_name` 不参与并发锁键，仍沿用 `threadId + runId` 生命周期管理。
- 不改变 `RunFinished` 终止语义。
- 保持客户端中断时的 cancel/cleanup 行为不变。
- `model_name` 非字符串类型时返回 `400` + `{"detail":"model_name must be a string"}`。

---

## 3. 前端设计

### 3.1 模型切换器（`ModelSelector`）

- **位置:** 顶部 Header（`page.tsx` 顶部控制区）
- **数据源:** 本地可选模型数组（首版静态）
- **状态归属:** `page.tsx` 的 `selectedModel`
- **联调方式:** 调用 `sendMessage(text, selectedModel)` 时透传

建议选项（首版）：

- `glm-4`
- `glm-4v`
- `glm-4.7`

### 3.2 `useAgentChat` 参数扩展

- `sendMessage(text: string)` 扩为 `sendMessage(text: string, modelName?: string)`
- `fetch("/api/chat")` 请求体新增 `model_name`
- 兼容旧调用：未传 `modelName` 时不发送或发送 `undefined`

### 3.3 任务看板（`TaskProgressBar`）

- **放置位置:** 消息列表上方（`ChatArea` 内）
- **拉取策略:** 组件内部每 2 秒轮询 `/api/task-status`，首次挂载立即请求
- **渲染策略:** 横向展示 6 个模块节点；完成节点显示勾选/高亮
- **悬浮交互:** hover 模块展示 steps 明细状态（tooltip/popover）
- **异常策略:** 拉取失败保留最近成功数据，避免 UI 闪烁
- **生命周期约束:** 组件卸载或页面 `hidden` 时暂停轮询；恢复可见后立即拉取一次
- **轮询终止条件:** 当 `overall.doneCount === overall.totalCount` 或收到明确终止信号（如当前会话的 `RunFinished`）时，主动清理定时器并停止轮询

---

## 4. 数据流（端到端）

1. 用户在 Header 选择模型（`selectedModel` 更新）。
2. 用户发送消息时，`sendMessage` 将 `model_name` 一并发送到 `/api/chat`。
3. 后端本次 run 使用该模型执行，并在 `RunStarted` 回显模型名。
4. `TaskProgressBar` 每 2 秒读取 `/api/task-status` 并刷新进度节点。
5. 模块 hover 时展示子步骤完成情况。

---

## 5. 风险与回归点

- **模型参数未透传到底层:** 需用日志或 `RunStarted.model` 验证实际生效。
- **模型回显闭环:** 前端在收到 SSE `RunStarted` 后应读取 payload 的 `model` 并更新当前会话模型标签，避免仅展示下拉框值导致“显示与实际执行模型不一致”。
- **任务状态文件脏数据:** 通过 `500 + detail` 提前暴露，避免静默错误。
- **前端渲染开销:** `TaskProgressBar` 状态局部化，避免影响主消息流与输入性能。
- **前后端可选模型不一致:** 前端静态列表仅做便捷入口；后端对未知模型走 provider 报错路径并输出排障日志。

---

## 6. 验收标准

- `/api/task-status` 可稳定返回（有文件返回文件，无文件返回默认模板）。
- `/api/chat` 可接受 `model_name` 且同会话并发控制行为不变。
- UI 可切换模型并对下一次请求生效。
- 任务看板可自动轮询刷新，并显示模块与子步骤状态。
- `task_progress.json` 非法 JSON 时，`/api/task-status` 返回 `500` 且错误体为 `{"detail":"..."}`。
- `model_name` 缺失、空字符串、非字符串三种输入行为可预期且可测试。
- `RunStarted.model` 与 provider 实际调用模型一致（通过日志或测试桩断言）。
