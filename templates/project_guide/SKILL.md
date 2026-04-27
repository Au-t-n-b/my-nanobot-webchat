# 项目引导（project_guide）

---
name: project_guide
description: 冷启动 + 阶段衔接 + 角色守门：结合登录用户阶段角色与 task_progress 真值，给出三分支引导。
version: 0.4.0
tags: [guide, cold-start, phase-transition, role-guard, skill-first]
---

## 部署位置

- 技能目录应位于与后端 `get_skills_root()` 一致的路径，例如：
  `%USERPROFILE%\.nanobot\workspace\skills\project_guide\`
- 关键资源：
  - `data/phases.json`：**阶段顺序单一真值表**（中文阶段名 ↔ moduleId ↔ skillDir ↔ startAction）。
  - `runtime/phase_rules.py`：纯函数 `load_phases / compute_order_cur / compute_order_user / is_admin_role / decide_branch`，**只算不写**。
  - `runtime/driver.py`：**Skill-First 驱动**，由 `skill_runtime_start(action=cold_start|guide_next_phase)` 触发，自己读资源、自己派生、自己 emit `chat.guidance`。

## 当前主路径：driver 直出（v0.4 起）

> 早期版本走"主 Agent 读 SKILL.md → LLM 自己生成话术"，但 LLM 路径会因长上下文 / 工具调用中断 / 路径理解偏差导致引导漏读 `users.json` `project_members.json`、给出错误结论。
> v0.4 起改为 **driver 主导**：判定逻辑全部在 `phase_rules.py`，driver 直接产出 `GuidanceCard`，前端按钮点了直接发 `skill_runtime_start` 进下一阶段，**不再经 LLM 推理**。

### 触发路径

| 时机 | 触发方 | 入参（`request.result`）要点 |
|---|---|---|
| 冷启动 / 新会话进入 | 前端 Workbench effect 直接发 `chat_card_intent.skill_runtime_start` | `userId` / `workId` / `projectId`；不带 `transition` |
| 阶段 SKILL 收尾 | `job_management` / `zhgk` / `jmfz` driver 内部调 `make_phase_guide_handoff_event` | `transition.{from_module,to_module}` + `transition_id` |
| 进展文件外部变更 | 后端文件钩子（可选，B 路径） | 由钩子合成 transition |

> 三种触发都最终落到 `dispatch_skill_runtime_intent → resume_runner → run_skill_runtime_driver(project_guide)`，driver 不区分场景，统一按"现状 + 可选 transition"派生。

## 阶段顺序与三套 ID（**真值在 `phases.json`**）

| order | 中文阶段名 (`displayName`) | `moduleId` | `skillDir` | `startAction` |
|---|---|---|---|---|
| 0 | 作业管理 | `job_management` | `job_management` | `jm_start` |
| 1 | 智慧工勘 | `smart_survey` | `zhgk` | `start` |
| 2 | 建模仿真 | `modeling_simulation_workbench` | `jmfz` | `start` |

- `displayName` 必须与 `project_members.json.stages[]` 中文名**完全一致**；不一致请改 phases.json，**不要**在话术里 patch。
- `startAction` / `startRequestId` 决定 driver 渲染的"启动下一阶段"按钮要发什么 intent；新增阶段 = 同时补这两个字段。
- 若 `task_progress.json` 还有 `system_design / device_install / sw_deploy_commission` 等条目，**当前版本只看前 3 阶段**；扩到 6 阶段时增量改 phases.json，不动判定代码。

## 派生量（与 `phase_rules.py` 等价）

```text
phases       = load_phases(phases.json)
order_cur    = phases 中第一个『tasks 全部 completed=true』为 false 的阶段 .order
                若都完成 → len(phases)
order_user   = member_stages 命中 phases.displayName 中的最小 order；命中不到 → null
is_admin     = users.json[当前用户].roleCode ∈ phases.json.admin.roleCodes
member_role  = project_members.json[当前用户当前项目].memberRole
```

## 三分支判定（**唯一来源 = `phase_rules.decide_branch`**）

| 条件 | 分支 | 文案大意 | CTA |
|---|---|---|---|
| `order_cur ≥ len(phases)` | `done` | 全部阶段已完成，可进入复盘/归档 | 无 |
| `is_admin` | `admin` | 管理员视角：当前阶段 X，可直接进入或查看任一阶段 | `skill_runtime_start` → `phases[order_cur].skillDir` |
| `member_role == "viewer"` | `wait` | 你是只读成员，可查看进度但不发起主流程 | 无 |
| `order_user is None` | `unknown` | 未在成员表中找到你的 stages，请联系管理员 | 无 |
| `order_user > order_cur` | `wait` | 你负责的「user 阶段」未到，前序仍在「cur 阶段」，请等待 | 无 |
| `order_user < order_cur` | `passed` | 你的「user 阶段」已结束，已进入「cur 阶段」，可只读/复盘 | 无 |
| `order_user == order_cur` | `proceed` | 轮到你了：可启动 `skillDir` 继续推进 | `skill_runtime_start` → `phases[order_cur].skillDir` |

> 若调用方传入 `transition.{from_module,to_module}`，文案前缀会变成「{from} 已完成 ✅，下一阶段：{to}。」并产出 `transition_id` 供前端做幂等。

## driver 行为规约

driver 的"输入 / 副作用 / 输出"必须保持以下不变量，避免回到 LLM 路径的不可控：

1. **只读，不写**：driver 不修改 `task_progress.json`、不写 registry。三阶段 SKILL 才负责写。
2. **零外部依赖**：仅依赖标准库 + 同目录的 `phase_rules.py`。不导入 nanobot 包。
3. **永不抛错出 main**：任何 I/O 异常都打 stderr + 输出兜底 `chat.guidance`，让 resume_runner 仍以 ok 回到前端。
4. **稳定 cardId**：`project_guide:<thread_id>:<transition_id|cold>`。重复触发会替换上一张卡，不堆叠。
5. **当前用户解析顺序**：`result.userId → result.workId/employeeNo → users.lastLoginAt 最近者`。前两个是显式 hint（前端冷启时塞），最后一个仅本地演示兜底。

## 与三阶段 SKILL 的衔接（占位钩子）

阶段 SKILL 在**收尾**那一步（例如 `job_management` 的 `jm_apply_schedule_draft` 完成后、`zhgk` / `jmfz` 同理）应**额外**发：

```text
1. task_progress.sync 把本阶段标 completed（已有逻辑）
2. skill_runtime_start，目标 = project_guide
   payload.transition = { from_module: <本阶段 moduleId>, to_module: <下一阶段 moduleId> }
   payload.transition_id = `${from}->${to}@${task_progress.updatedAt}`
```

构造 helper：`phase_rules.make_phase_guide_handoff_event(...)`。

> **三阶段业务驱动的接入留给后续 PR**，本 PR 只交付 driver + 真值表 + 单测。详见 `docs/specs/phase_guide.md`。

## 给同事的交接

- **改阶段顺序 / 增删阶段** → 只改 `data/phases.json`（含 `startAction`），不动 driver。
- **改文案口吻** → 改 `phase_rules.decide_branch` 的模板字符串；driver 是渲染层，不含话术。
- **角色策略改动**（admin / viewer / 多 stages） → 改 `phases.json` 与 `phase_rules.py`，并在 `tests/skills/test_project_guide_phase_rules.py` 增/改对应单测。
- **想退回 LLM 路径调试** → 临时把前端 `WorkbenchContent.tsx` 的冷启动 effect 改回 `sendChatRequest(coldPrompt)` 即可；driver 路径与 LLM 路径完全独立、互不依赖。

## 兼容性注记

- v0.3 之前 driver 是空占位、靠主 Agent 读本文档生成话术；如果某些环境还没升级 v0.4 driver，
  resume_runner 会得到 0 个事件、前端不会显示卡——表现为"冷启动静默"，但**不会报错**。
- 升级 v0.4 时**只需替换 driver.py 与 phases.json**，前端事件契约不变（仍是 `chat.guidance`）。
