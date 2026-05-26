# Nanobot 混合模式协议（Skill-First + 受控 Agent 子任务）

## 1. 设计原则

- **流程主权在 `driver`**：步骤迁移、HITL、artifact 发布、epilogue 仍由 skill runtime driver 打印的标准事件驱动。
- **Agent 只做步骤内认知**：分析、抽取、比对、总结；**不得**通过新 verb 直接推进 driver 状态机。
- **UI 与恢复仍走平台通道**：`task_progress.sync`、`dashboard.patch`、`chat.guidance`、`SkillUiDataPatch` 的 `syntheticPath + docId + revision` 路由规则不变；子任务禁止绕过这些 emit 直接改前端私有状态。

## 2. 运行时事件：`skill.agent_task_execute`

由 driver 在 stdout 打印一行 JSON **信封**（与其它 `skill.*` / `dashboard.*` 事件一致），由 `skill_resume_runner` 顺序 `await emit_skill_runtime_event` 处理。

### 2.1 信封字段（顶层）

| 字段 | 类型 | 说明 |
|------|------|------|
| `event` | string | 固定为 `skill.agent_task_execute` |
| `threadId` | string | 会话线程 ID（平台侧会以当前 chat 的 `thread_id` 覆盖/校正） |
| `skillName` | string | 技能名 |
| `skillRunId` | string | 本次 skill run id |
| `timestamp` | number | 可选，毫秒时间戳 |
| `payload` | object | 见下表 |

### 2.2 `payload`：子任务请求（最小集）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `taskId` | string | 是 | 子任务唯一 ID，建议含 `requestId` 前缀，便于日志与幂等 |
| `parentRequestId` | string | 否 | 父级 `skill_runtime_start` / resume 的 `requestId`，用于追踪 |
| `skillName` | string | 否 | 可与信封顶层重复；bridge 优先信封 |
| `stepId` | string | 是 | driver 内步骤语义 ID（如 `zhgk.step1.hybrid_scene_digest`） |
| `goal` | string | 是 | 给受控 Agent 的自然语言目标 |
| `allowedTools` | string[] | 否 | 工具白名单，默认 `["read_file","list_dir"]` |
| `maxIterations` | number | 否 | LLM+工具循环上限，默认 8 |
| `resultSchema` | object | 否 | 预留：例如 `{ "type": "string" }` / JSON Schema；当前实现以纯文本结论为主 |
| `syntheticPath` | string | 是 | 目标大盘 `skill-ui://SduiView?...` |
| `docId` | string | 是 | 与 `SkillUiDataPatch` 对齐的文档 ID |
| `summaryNodeId` | string | 否 | `dashboard.patch` 合并目标节点 id，默认 `summary-text` |
| `summaryNodeType` | string | 否 | merge 目标节点的 SDUI `type`，须与 dashboard JSON 一致，默认 `Text` |

### 2.3 模块状态（终端态）

混合模块 `hybrid:{skillName}` 的 `status` 取值包括：`running`（执行中）、`completed`（成功结束）、`failed`（子任务执行失败）、`skipped`（无 Agent 会话等跳过）。**不得**将失败或跳过误标为 `completed`。

### 2.4 平台行为摘要

1. 发出 `task_progress.sync`：模块 id 建议为 `hybrid:{skillName}`，表示「受控 Agent 子任务」轨道（与 registry 模块并存时由前端 `mergeTaskStatusSnapshot` 按模块 id 合并）。前端总览进度条在汇总 `overall` / `summary` 时会 **排除** `hybrid:` 前缀模块，避免污染主项目完成度。
2. 若当前请求上下文存在 `AgentLoop`：在 **同一 await 链**内执行受控子循环（白名单工具 + 最大迭代），得到文本结论。
3. 若不存在 `AgentLoop`（单测 / 无 SSE 绑定）：子任务标记为跳过，不调用模型。
4. 可选：对 `summaryNodeId` 对应节点发出 `SkillUiDataPatch`（`merge` `Text` 的 `content` 等字段）。

## 3. Shared Skill State（逻辑分区）

以下为 **逻辑** 分区，便于 driver 与 Agent 对齐；物理上仍可落在 `skill_result.json`、dashboard 节点、或后续专用 store。

| 分区 | 用途 |
|------|------|
| `inputs` | 用户上传、Start 表、路径等 |
| `stepStatus` | driver 步骤机状态 |
| `agentTasks` | 子任务元数据：`taskId`、`stepId`、`status`、`allowedTools`、起止时间 |
| `analysis` | Agent 结论文本或结构化结果（与 `resultSchema` 对齐） |
| `artifacts` | 仍由 `artifact.publish` 等事件驱动 |
| `decisions` | HITL 选择、确认结果 |

## 4. 与现有能力的关系

- **兼容** `gongkan_skill`、`tool_lab`、`request_user_upload` / `present_choices`：不占用 `resumeAction` 文本通道表达子任务语义。
- **不替代** `skill_runtime_start` / `skill_runtime_result`：子任务发生在某次 resume 处理过程中的一段同步计算。

## 5. 跨刷新恢复（后续）

当前 MVP 在 bridge 内同步完成子任务；若需刷新恢复，可在 `PendingHitlStore` 或并行表中扩展 `taskId -> threadId/requestId/status/result`（见路线图）。
