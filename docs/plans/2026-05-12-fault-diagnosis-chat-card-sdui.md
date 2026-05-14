# Fault Diagnosis Log Intake (图二) Chat Card — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在聊天区用 **`SkillUiChatCard` + 纯 SDUI 节点树** 实现「日志与现象接入」图二交互（Tabs + 上传 + 多行输入 + 确认启动），且不通过自定义组件截胡 `ChatCardBubble`，从而**不扩大对现有聊天卡与其他功能的回归面**。

**Architecture:** 业务侧（Skill driver 或独立 Agent tool）在需要时通过已存在的 SSE 通道下发 `SkillUiChatCard`；`payload.node` 仅由 `Stack` / `Tabs` / `FilePicker` / `HitlTextInput` / `ConfirmCard` 等**已有 SDUI 类型**组合而成；用户操作回传沿用 `chat_card_intent` → `skill_runtime_result` 与现有 HITL 持久化。推荐 **多步 HITL**（先文件、再文本、再确认）以降低「单卡双输入聚合」的协议复杂度；若坚持单卡聚合，须在 Skill 内用 `stateNamespace`/会话状态自行合并，平台不编排业务。

**Tech Stack:** Next.js（`frontend/components/MessageList.tsx`、`SduiNodeView`）、Python（`nanobot/web/routes.py` SSE、`nanobot/agent/loop.py` 的 `emit_skill_ui_chat_card_event`、`nanobot/web/mission_control.py` 可选参考）、SDUI 协议（`frontend/lib/sdui.ts`）、现有测试框架（`tests/web/`）。

---

## 原则（硬性，与「不影响其他功能」直接相关）

| 必须 | 禁止 |
|------|------|
| 卡片内容只走 `payload.node` → `SkillUiRuntimeProvider` → `SduiNodeView` | 在 `MessageList` / `ChatCardBubble` 内按标题或 skill 名分支渲染**整块自定义 React 卡** |
| 复用 `Tabs`、`FilePicker`、`HitlTextInput`、`ConfirmCard` | 手写原生 `Tab` / `textarea` / 无协议 `button` 冒充图二 |
| 主确认走 `ConfirmCard` 或等价 `skill_runtime_result` | 仅 `Button` + `post_user_message` 冒充「已提交诊断」 |
| 使用稳定且唯一的 `cardId`，`docId` 与现有会话策略一致 | 全局修改 `SduiNodeView` / `SkillUiRuntimeProvider` 的默认行为（除非全平台需求并已评审） |

---

### Task 0: 对齐验收与数据流（无代码）

**产出：** 一页纸写清：谁触发卡片（工具名 / Skill 入口）、每一步 `requestId` 是否复用、刷新后回放期望。

**验证：** 与 `docs/skill/guide.md` 中「平台不解释业务」一致：分支与聚合逻辑全部在 Skill。

---

### Task 1: 定义图二 SDUI JSON（常量或模板）

**Files:**

- Create（推荐其一）: `nanobot/agent/tools/fault_diagnosis_intake_card.py` 内嵌 `CHAT_CARD_NODE` 常量，或  
- Create: `tmp-run/manual-verify/skills/<demo_skill>/references/intake_chat_card.json`（仅本地验证）

**内容要点：**

- `node.type`: `Stack`，子节点顺序：`Markdown` 或 `Text`（引导语）→ `Tabs`（`defaultTabId` + 两个 `tabs[]`，每 tab `children`）→ 可选 `Row` 底部区。
- Tab「提供故障日志」：`FilePicker`（`purpose`、`accept`、`skillName`、`hitlRequestId`、`saveRelativeDir` 等字段与现有 `SduiFilePicker` 一致）。
- Tab「描述问题现象」：`HitlTextInput`（`rows`、`placeholder`、`submitLabel`、`skillName`、`hitlRequestId`）。
- 最终确认：`ConfirmCard`（`title`、`confirmLabel`、`cancelLabel`、`skillName`、`hitlRequestId`）。

**注意：** 若三步 HITL 使用**不同** `hitlRequestId`，则一张静态 JSON 无法同时绑定三个控件；此时应拆为 **三张顺序卡片 replace**，或 **单 requestId + Skill 内分字段读取多次 resume**（需与 `nanobot/web` 里 pending HITL 语义对齐后再定）。

**Step 1:** 与后端同事确认采用「单卡 + 单 requestId」还是「多卡 / 多 requestId」。

**Step 2:** 提交 JSON 模板到仓库（或 tool 常量）。

**Step 5: Commit**

```bash
git add <paths>
git commit -m "chore(diag): add SkillUiChatCard SDUI template for log intake"
```

---

### Task 2: 最小通路 — 仅推卡渲染（不接 HITL）

**Files:**

- Modify: 任选已有可调用路径，在 **一次 chat 请求** 中调用 `emit_skill_ui_chat_card_event`（见 `nanobot/agent/loop.py`）  
- 参考: `nanobot/web/routes.py` 中 `emit_skill_ui_chat_card` 闭包如何绑定到 agent

**Step 1:** 在本地或 demo 分支，让某条确定的用户指令（或测试-only route）触发一次 `SkillUiChatCard`，`payload` 含 `cardId`、`title`、`node`（Task 1 模板），`placeholder` 的 `skillName`/`hitlRequestId` 可先填空字符串以观察 **纯 UI**（部分按钮会禁用，属预期）。

**Step 2:** 浏览器打开会话，确认出现图二布局，且**其他历史消息与普通 markdown 气泡无回归**。

**Step 3: Commit**（若仅本地脚本可不提交，推荐加 `tests/web` 见 Task 4）

---

### Task 3: 接 HITL — Skill driver 或 tool 编排

**Files:**

- Create 或 Modify: Skill `runtime/driver.py`（或 `nanobot/agent/tools/*.py`）  
- Read: `nanobot/web/skill_runtime_bridge.py`（事件名白名单）、`nanobot/web/skill_resume_runner.py`（resume 行为）

**Step 1:** `hitl.file_request` → 下发带 `FilePicker` 的 `SkillUiChatCard`（或同卡 replace）。用户「完成上传并继续」→ `skill_runtime_result` 带 `upload`/`uploads`。

**Step 2:** `hitl.text_request` → replace 或 append 下一张带 `HitlTextInput` 的卡。

**Step 3:** `hitl.confirm_request` 或卡内 `ConfirmCard` → 用户确认后 resume，Skill 输出 `chat.guidance` 或下一步事件。

**验证：** 每步仅一个 pending HITL；`requestId` 幂等；取消路径有定义。

**Step 5: Commit**

```bash
git commit -m "feat(diag): wire log intake chat card to HITL resume"
```

---

### Task 4: 自动化测试（推荐，防回归）

**Files:**

- Create: `tests/web/test_fault_diagnosis_chat_card_payload.py`（或扩展现有 `test_skill_runtime_bridge.py` / chat 相关测试）

**Step 1:** 构造最小 `payload` dict，断言经与生产相同路径 **normalize** 后的 `node` 类型树包含 `Tabs`、`FilePicker`、`HitlTextInput`（字符串或递归断言），且**不包含** `ChoiceCard`（若本工具不应出现选择题）。

**Step 2:** 运行：

```bash
pytest tests/web/test_fault_diagnosis_chat_card_payload.py -v
```

**预期:** PASS。

**说明:** 若不便在单测里绑 SSE，可只测「payload → normalizer」函数（若已有则复用 `frontend` 的归一化逻辑需在 Node 侧镜像，或以 Python 侧 `mission_control` 使用的结构为准）。

---

### Task 5: 文档与团队对齐

**Files:**

- Modify: `docs/skill/cursor-sop.md` 或 `docs/skill/guide.md` 增加一小节「聊天区复合卡验收清单」（可选，需你方确认后再改）

**内容:** 链接本计划 + 三条硬性原则（不截胡 `SduiNodeView`、不用手写表单冒充 SDUI、主按钮协议）。

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 同事为赶 UI 在 `ChatCardBubble` 加特判 | Code review 对照本计划「原则」表；CI 可加 grep 禁止新 import `*ClawLogAccess*` 类特判（按需） |
| 单卡多控件共享 `hitlRequestId` 行为未定义 | Task 3 实施前与 `PendingHitlStore` 行为对齐文档 |
| `FilePicker` + `HitlTextInput` 同一屏两次 submit | 优先多步卡；单屏必须经 Skill 状态合并设计评审 |

---

## 执行方式（计划落地后）

**Plan complete and saved to `docs/plans/2026-05-12-fault-diagnosis-chat-card-sdui.md`. Two execution options:**

1. **Subagent-Driven（本会话）** — 每 Task 派子代理 + Task 间人工 review  
2. **Parallel Session（新会话）** — 新会话使用 superpowers:executing-plans 按 Task 批量执行并设检查点  

**Which approach?**（由你或 Tech Lead 选定。）

---

## 参考代码锚点

- 聊天卡渲染: `frontend/components/MessageList.tsx`（`ChatCardBubble` → `SkillUiRuntimeProvider` → `SduiNodeView`）
- SSE 下发: `nanobot/web/routes.py`（`SkillUiChatCard`）、`nanobot/agent/loop.py`（`emit_skill_ui_chat_card_event`）
- 可选业务封装参考: `nanobot/web/mission_control.py`（`emit_chat_card` 用法）
- SDUI 类型与 ChatCard 载荷: `frontend/lib/sdui.ts`（`SkillUiChatCardPayload` 等）
