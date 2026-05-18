# 混合模式治理与检查清单

本文档配合 `docs/hybrid-mode-protocol.md` 与样板 `templates/gongkan_skill/runtime/driver.py` 使用。

## 何时必须 Skill-First

- 需要 **确定性步骤顺序**、审批、上传、产物分发、与 `PendingHitlStore` 绑定的 HITL。
- 需要 **可重复执行** 且便于审计的交付流程（工勘类场景）。

## 何时允许委托受控 Agent

- 单步内的 **认知型** 工作：摘要、比对、从已有文件中抽取字段说明、风险措辞草稿等。
- 不替代 driver 决策「下一步去哪」；子任务 **返回结构化/文本结果** 后仍由 driver 继续发 `dashboard.patch` / `chat.guidance` 等。

## 进度与总览（P1）

- `hybrid:{skill}` 模块的 TaskStatus 仅用于工作台局部提示（如 StepLogs），**不参与** `projectOverviewStore` 中 `overall.totalCount` / `completedCount` 及 `summary` 的聚合。
- 子任务终端态使用 `completed` / `failed` / `skipped`，不得用 `completed` 表示失败或跳过。

## 子任务能否二次 HITL

- **当前平台 MVP**：`skill.agent_task_execute` 内 **不** 挂载 `request_user_upload` / `present_choices` 等会阻塞 resume 链路的工具；子任务应为 **纯工具 + LLM**、在同一次 `await` 内结束。
- 若未来需要二次 HITL：须单独设计 **可恢复** 状态机（扩展 `PendingHitlStore` 或独立表），避免阻塞 `skill_resume_runner` 的 stdout 顺序语义。

## 结果 schema

- `payload.resultSchema` 为预留字段；当前实现以 **纯文本** 写入 dashboard 目标节点（默认 `summary-text`）。
- 若引入 JSON 结果：须约定 `resultSchema` 与 `merge` 目标节点类型，并在 bridge 内做校验与截断。

## 新 skill 检查清单

1. **协议**：子任务是否使用 `skill.agent_task_execute` + 文档中的 payload 字段，而非塞进 `resumeAction`。
2. **工具白名单**：`allowedTools` 是否最小化；是否禁止 `exec` / 网络除非明确需要。
3. **预算**：`maxIterations` 上限是否合理（建议 ≤ 16）。
4. **路由**：`syntheticPath` / `docId` / `summaryNodeId` 是否与该 skill 的 `dashboard.json` 一致。
5. **Emitter**：在真实 AGUI 会话中验证 Fastlane/chat 已绑定 `task` / `patch` emitter（见 `routes.py`）。
6. **测试**：至少覆盖「无 `AgentLoop` 跳过」「有 loop 时 patch 发出」；样板 skill 覆盖一次 driver 路径。

## 可复制模板

- **Driver**：`templates/gongkan_skill/runtime/driver.py` 中 Step1 完成后的 `_print_event({ "event": "skill.agent_task_execute", ... })`。
- **Bridge**：`nanobot/web/skill_runtime_bridge.py` 中 `_emit_skill_agent_task_execute`。
- **前端类型与提示**：`frontend/lib/skillHybridProtocol.ts`、`StepLogs` 的 `hybridSubtaskHint`。
- **测试**：`tests/web/test_skill_agent_task_execute.py`。
