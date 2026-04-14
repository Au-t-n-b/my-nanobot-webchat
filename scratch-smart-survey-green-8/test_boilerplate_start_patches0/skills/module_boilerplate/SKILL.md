---
description: 模块参考样板 — 三块大盘（进展/指标/产物）+ 会话内嵌 HITL（选择、上传）
---

# module_boilerplate

标准 **模块案例模板**：供业务在 `skills_root/module_boilerplate/` 交付 `module.json` + `data/dashboard.json`，通过工具 **`module_skill_runtime`** 驱动大盘 **SkillUiDataPatch** 与会话内 **SkillUiChatCard**（Guidance / Choice / FilePicker）。

这个模板专门服务于你描述的场景：

- 一个业务会拆成多个模块，每个模块内部再由若干 Skill 实现。
- 每个模块开跑前，必须先打开对应模块大盘。
- 模块执行过程中，左侧通过 **HITL 选择 / 文件上传** 推进；右侧大盘同步展示 **当前进展 / 黄金指标 / 产物总结**。
- 业务同事可以在这个案例基础上替换自己的文案、指标与图表内容，但保留同一套交互骨架和 Patch 契约。

## 何时调用

- 用户要「跑模块样板」「演示 HITL 与大盘」或需要参考端到端链路时。
- 必须在 **Web 聊天** 上下文中调用（需要 `thread_id`），否则 Patch/卡片不会推送到前端。

## 参数

- `module_id`：固定为 **`module_boilerplate`**（目录名一致）。
- `action`：见下表。
- `state`：可选 JSON；HITL 回调会合并 `standard`（策略选项 id）、`upload`（文件信息）、`cardId` 等。

## action 顺序

| action | 说明 |
|--------|------|
| `guide` | 初始化大盘 + 引导卡片（启动 / 取消）；**模块执行前必须先调它，用于打开模块大盘** |
| `start` | 开始执行段，更新指标 |
| `choose_strategy` | 下发选择卡片（通常由 `start` 后助手调用；用户选完后前端自动进入 `upload_evidence`） |
| `upload_evidence` | 下发 **FilePicker** 拖拽上传卡片（须由本工具调用；**禁止**用 `present_choices` 模拟上传） |
| `after_upload` | 上传完成后的处理（通常由 FilePicker 自动回调） |
| `finish` | 交付总结与产物；模板会生成一个可预览的 `.md` 交付说明 |
| `cancel` | 取消并清理会话状态 |

### flowOptions 与默认顺序（`module.json`）

模板默认 **`requireEvidenceBeforeStrategy: true`** 时，顺序为：

1. `guide` → `start`
2. **`start`**：若 `skills/<module_id>/input/` 下**尚无文件**，则**只**下发 **FilePicker**（`ask_for_file`），下一步为 `resume_after_evidence_gate`（由上传成功自动触发，无需模型再调上传类工具）。
3. 上传完成后进入 **策略 ChoiceCard**（`choose_strategy` / `resume_after_evidence_gate` 内部已衔接）。
4. 选策略 → `upload_evidence`（若门禁阶段已上传且会话里已有 `fileId`，可能直接进入 `after_upload`）→ `after_upload` → `finish`。

若将 **`requireEvidenceBeforeStrategy`** 设为 **`false`**，则恢复「先策略、再上传」：`start` 后助手应调用 `choose_strategy`，再 `upload_evidence`。

### `dataFile` 与右栏 Patch 路由

`module.json` 里的 **`dataFile`** 经 `skill-ui://SduiView?dataFile=...` 发出后，必须与前端大盘占位路径**一致**（建议沿用模板：`workspace/skills/<module_id>/data/dashboard.json`）。若与侧栏自动登记的 `syntheticPath` 不一致，**SkillUiDataPatch 会被丢弃**，表现为 Stepper/黄金指标不更新而误以为只有文案区变化。

典型首次调用：

```json
{ "module_id": "module_boilerplate", "action": "guide", "state": {} }
```

用户点「启动样板」后等价于 `action: "start"`。策略在 **ChoiceCard** 内确认；若用户只回了策略 id 文本（如 `balanced`），你应直接调用 `upload_evidence` 并传入 `state.standard`。上传必须由 **`upload_evidence`** 触发内嵌拖拽区，不要再用选择题冒充上传。

## 给业务同事的改造边界

- 可以改：标题、步骤文案、策略选项、指标名、图表内容、产物名称、总结文案。
- 应尽量保留：`guide -> start -> choose_strategy -> upload_evidence -> after_upload -> finish` 这套节奏。
- 不要改：`module.json.dataFile` 与真实大盘路径的对应关系，以及 `dashboard.json` 中被 Patch 命中的稳定节点 id。

## 推荐复制方式

1. 复制整个 `module_boilerplate/` 目录为你们自己的 `<module_id>/`。
2. 先在 `module.json` 的 `caseTemplate` 中改模块标题、目标、策略选项、指标名称、交付说明文件名。
3. 再按你们业务需要改 `data/dashboard.json` 的图表布局和文案。
4. 最后才改 `module_skill_runtime.py` 里的业务逻辑与实时 Patch 数值。

## 人类可读流程

详见同目录 `references/flow.md`。

## 安装

将本目录复制到 **`~/.nanobot/workspace/skills/module_boilerplate`**（与 `module_id` 同名），确保存在 `module.json` 与 `data/dashboard.json`。
