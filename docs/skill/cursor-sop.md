# Cursor SOP：用 AI 快速构建阶段 Skill（Skill‑First / SDUI）

本 SOP 面向“业务 Skill 开发同事”：用 Cursor 的 AI 协助，把你设计好的 **业务逻辑（状态机）** 与 **UI（SDUI/EmbeddedWeb）** 落到一个可运行的阶段 Skill。

> 目标：**从 0 到能跑**（能挂载模块大盘 + driver 能 patch + 可扩展到 HITL / 产物 / 串下一阶段）。  
> 约束：遵守 [`docs/skill/guide.md`](./guide.md) 的 Skill‑First 边界；遵守 [`docs/sdui/protocol.md`](../sdui/protocol.md) 的 SDUI 协议。

---

## 0. 开工前：准备 3 样“输入材料”

你只要准备下面三段信息，后面全都可以交给 Cursor 逐步落地：

1) **阶段定义（1 段话）**：本阶段做什么、输入是什么、输出产物是什么。  
2) **状态机表（强烈建议写成表格）**：  
   - `state`：每个阶段状态（如 `start/upload/running/publish/done/cancelled`）  
   - `action`：每个触发动作（如 `start`, `resume_after_upload`, `publish`, `fallback_cancel`）  
   - `event`：每个动作要输出哪些事件（`dashboard.patch` / `hitl.*` / `artifact.publish`）  
3) **UI 草图**：选择一种形态并写出节点清单：\n   - 纯 SDUI（Stepper/Statistic/TextArea/Button/ArtifactGrid）\n   - 本地 HTML 工作台（EmbeddedWeb + state 下发 + postMessage 上行）\n   - 外链 iframe（EmbeddedWeb 外链）

---

## 1. 选一个 starter 当骨架（不要从空文件开始）

在仓库根 `skill-starters/` 选一个最接近你的阶段的 starter：  

- **本地 HTML 工作台型**：`skill-starters/stage-starter-local-html/`  
- **外链 iframe 型**：`skill-starters/stage-starter-external-web/`  
- **纯 SDUI 型**：`skill-starters/stage-starter-native-sdui/`

把 starter 目录复制到本机：`~/.nanobot/workspace/skills/`，并把目录名改成你的 skill 名（例如 `stage4_delivery`）。

---

## 2. 在 Cursor 里对 AI 的“第一条指令模板”（建议照抄）

把下面这段直接发给 Cursor（把尖括号内容替换成你自己的）：  

```text
我要实现一个新的阶段 Skill，遵守 Skill-First。

阶段技能名（目录名/moduleId）: <stage4_delivery>
docId: <dashboard:stage4-delivery>
UI 形态（选一项）: <纯SDUI | 本地HTML工作台 | 外链iframe>

业务目标（1-3 句）:
<...>

状态机（action -> 事件输出）:
- start: chat.guidance + dashboard.patch(初始化 Stepper/指标) + (如需输入则 hitl.* 并退出)
- <resume_after_xxx>: 校验 skill_runtime_result -> dashboard.patch -> ...
- publish: artifact.publish + dashboard.patch(100%)
- fallback_cancel: dashboard.patch(降级/终止)

UI 结构要点（节点 id 必须稳定）:
- Stepper id=stepper-main
- 指标区: StatisticRow id=stats-row，含 stat-progress/stat-status/...
- （如 EmbeddedWeb）id=<workbench-web> src=<...> state=<...>
- ArtifactGrid id=artifacts

请你基于仓库的 stage starter 修改以下文件，使其能跑通最小闭环（不做业务细节）:
- module.json
- data/dashboard.json
- runtime/driver.py
- (如本地HTML) ui/workbench.html

要求:
- driver 只通过 stdout NDJSON 输出事件信封，不要阻塞等待输入
- dashboard.patch 只做 by-id merge 叶子字段（遵守 SDUI Patch 约束）
- 不要修改前端/后端平台代码
```

这条指令的目标是：**让 AI 先把骨架跑通**，而不是一次性写完全部业务。

---

## 3. 让 AI 分三轮交付（每轮都可运行/可验证）

### 第 1 轮：只做“能挂载 + 能 patch”

验收标准（必须全部满足）：  
- 打开工作台能看到模块大盘（SDUI 渲染正常）  
- driver 一启动就能 patch 一个 `Statistic` 或 `Markdown`（例如进度从 0% 到 30%）  

### 第 2 轮：加入 HITL（文件/文本/选择/确认）

让 AI 按 [`docs/skill/guide.md`](./guide.md) 的 Yield/Resume 约束补：  
- `hitl.file_request` / `hitl.text_request` / `hitl.choice_request` / `hitl.confirm_request`  
- `requestId/resumeAction/onCancelAction` 全部齐全  
- `fallback_cancel` 必须可安全执行

### 第 3 轮：加入产物与预览

让 AI 补：  
- `artifact.publish` 发布产物索引（让右侧 PreviewPanel 能预览）  
- 大盘 `ArtifactGrid` 里能看到发布的条目  

---

## 4. EmbeddedWeb（本地 HTML 工作台）专项 SOP

如果你的阶段是“本地 HTML 工作台型”，建议把这段要求加进对 AI 的指令：  

- `dashboard.json` 的 `EmbeddedWeb.src` 使用：  
  `/api/file?path=workspace/skills/<skill>/ui/<page>.html`  
- driver 用 `dashboard.patch` merge `EmbeddedWeb.state` 下发状态（JSON）  
- HTML 内用 `window.parent.postMessage({ type: \"skill_web_intent\", payload: { action, data } }, \"*\")` 上行事件  

---

## 5. 常见踩坑（让 AI 避免）

- **模块挂载失败**：`module.json.dataFile` 不等于 `skills/<skill>/data/dashboard.json`  
- **Patch 不生效/串台**：节点没 `id` 或 `docId/syntheticPath` 不一致  
- **把业务逻辑写进平台**：违反 Skill‑First（见 [`docs/skill/guide.md`](./guide.md)）  
- **用 Patch 改结构**：Patch M1 不允许改 `children/tabs`，只能 merge 叶子字段（见 [`docs/sdui/protocol.md`](../sdui/protocol.md)）  

