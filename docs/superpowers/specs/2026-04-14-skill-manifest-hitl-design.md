# Skill Manifest HITL Design

**Goal:** 为 workspace skill 提供一套声明式通用交互能力，让 skill 开发者仅通过维护 skill 目录内文件即可触发文件上传卡与选择卡，而不必为每个 skill 手写 Python flow。

**Context**

当前系统中：
- `SKILL.md` 只作为 agent 说明文档加载，不会被解析成可执行规则。
- 会话内的 HITL 交互由后端显式触发，核心能力在 `module_skill_runtime.py` 与 `mission_control.py`。
- 前端已经具备成熟的 `FilePicker`、`ChoiceCard`、`chat_card_intent`、预览面板等基础组件。

因此，新方案不应尝试“让 SKILL.md 自己长出交互”，而应新增一层独立、可校验、可执行的 skill manifest。

---

## Design Summary

每个 skill 目录保持双文件模式：

- `SKILL.md`
  - 给人和 agent 阅读
  - 负责说明 skill 的用途、业务语义、人工使用方式
- `skill.manifest.json`
  - 给系统执行
  - 负责声明式描述通用交互 gate

系统新增一套 `skill manifest runtime`，读取 `skill.manifest.json` 后，将其中的声明翻译为现有 HITL 能力：

- `file_gate` -> `MissionControlManager.ask_for_file(...)`
- `choice_gate` -> `MissionControlManager.emit_guidance(...)`
- 用户回传 -> `chat_card_intent` -> runtime 恢复执行

该 runtime 只负责“通用交互 gate”，不负责：

- 复杂业务执行
- 项目总览 / 大盘指标更新
- 跨模块流程编排
- 替代现有 `module_skill_runtime`

---

## MVP Scope

第一阶段只支持：

1. `skill.manifest.json` 读取与校验
2. 两类 step
   - `file_gate`
   - `choice_gate`
3. 严格文件名存在校验
4. 文件上传卡触发
5. 选择卡触发
6. skill 运行状态持久化
7. `chat_card_intent` 恢复执行

第一阶段不支持：

- 表达式引擎
- 复杂条件判断
- 多层嵌套分支
- 自动更新右侧大盘
- 跨 skill 调用
- 将 manifest 内嵌到 `SKILL.md`

---

## Manifest Shape

顶层结构：

```json
{
  "version": 1,
  "entry": "prepare_inputs",
  "stateNamespace": "plan_progress",
  "steps": []
}
```

### `file_gate`

```json
{
  "id": "prepare_inputs",
  "type": "file_gate",
  "title": "请补齐输入文件",
  "description": "需要先上传两个输入文件才能继续。",
  "files": [
    {
      "label": "到货表.xlsx",
      "path": "workspace/skills/plan_progress/input/到货表.xlsx",
      "match": "strict"
    },
    {
      "label": "人员信息表.xlsx",
      "path": "workspace/skills/plan_progress/input/人员信息表.xlsx",
      "match": "strict"
    }
  ],
  "upload": {
    "saveDir": "skills/plan_progress/input",
    "multiple": true,
    "accept": ".xlsx"
  },
  "next": "choose_mode"
}
```

执行规则：

- 检查 `files[*].path`
- 全部存在 -> 返回 `completed + next`
- 任意缺失 -> 弹上传卡并返回 `blocked_by_hitl`
- 上传完成回传后重新校验，不直接信任回传 payload

### `choice_gate`

```json
{
  "id": "choose_mode",
  "type": "choice_gate",
  "title": "请选择处理模式",
  "description": "请选择本轮计划生成策略。",
  "options": [
    { "id": "balanced", "label": "均衡模式" },
    { "id": "speed", "label": "快速模式" }
  ],
  "storeAs": "mode",
  "nextByChoice": {
    "balanced": "run_balanced",
    "speed": "run_speed"
  }
}
```

执行规则：

- 弹出选择卡
- 用户选择后校验 `optionId`
- 将结果写入 runtime state 的 `values[storeAs]`
- 根据 `nextByChoice` 返回下一步

---

## Runtime Contract

建议统一入口：

```python
run_skill_manifest_action(
    skill_name: str,
    step_id: str | None,
    state: dict[str, Any],
    thread_id: str,
    docman: Any = None,
) -> dict[str, Any]
```

返回值约定：

```python
{"ok": True, "status": "completed", "next": "choose_mode", "state": {...}}
{"ok": True, "status": "blocked_by_hitl", "state": {...}}
{"ok": False, "error": "unknown step: choose_mode"}
```

推荐运行态：

```json
{
  "skill": "plan_progress",
  "currentStep": "choose_mode",
  "values": {
    "mode": "balanced"
  },
  "uploads": {
    "prepare_inputs": [
      "workspace/skills/plan_progress/input/到货表.xlsx",
      "workspace/skills/plan_progress/input/人员信息表.xlsx"
    ]
  }
}
```

---

## Integration Plan

建议新增文件：

- `nanobot/skills/manifest_schema.py`
  - 定义 schema 与最小校验
- `nanobot/skills/manifest_loader.py`
  - 读取 `skill.manifest.json`
- `nanobot/skills/manifest_runtime.py`
  - 执行 `file_gate` / `choice_gate`
- `nanobot/web/skill_manifest_bridge.py`
  - 将 runtime 结果桥接到 `ask_for_file` / `emit_guidance`

建议新增或扩展：

- `nanobot/web/routes.py`
  - 在 fast-path 中识别并消费 skill manifest intent
- `frontend/components/sdui/FilePicker.tsx`
  - 允许携带 `skillName` / `stepId` / `stateNamespace`
- `frontend/components/sdui/ChoiceCard.tsx`
  - 同上

推荐新增 verb：

- `skill_manifest_upload_complete`
- `skill_manifest_choice_selected`

这样可与现有 `module_action`、`choice_selected` 分层隔离，日志与调试更清晰。

---

## Testing Strategy

必须新增自动化测试：

1. schema 校验测试
2. loader 读取与报错测试
3. `file_gate`
   - 文件齐全
   - 文件缺失
   - 上传后重新校验通过
4. `choice_gate`
   - 合法选项
   - 非法选项
5. fast-path intent 测试
6. 前端 payload 结构测试

试点 skill 推荐：

- 新建最小 demo skill，或
- 以 `plan_progress` 做第一批落地验证

不建议第一批直接接入智慧工勘。

---

## Acceptance Criteria

完成后应满足：

1. skill 作者可以在 skill 目录新增 `skill.manifest.json`
2. 仅修改 manifest，即可定义：
   - 某路径下文件不存在时弹上传卡
   - 若文件存在则自动进入下一步
   - 某一步弹选择卡并记录用户选择
3. 无需为每个 skill 新增专属 Python flow 才能触发上述通用能力
4. 现有模块 flow 与大盘机制不被破坏
5. 所有新能力具备自动化测试覆盖
