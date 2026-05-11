# Cursor SOP：用 AI 快速构建阶段 Skill（Skill‑First / SDUI）

本 SOP 面向“业务 Skill 开发同事”：用 Cursor 的 AI 协助，把你设计好的 **业务逻辑（状态机）** 与 **UI（SDUI/EmbeddedWeb）** 落到一个可运行的阶段 Skill。

> 目标：**从 0 到能跑**（能挂载模块大盘 + driver 能 patch + 可扩展到 HITL / 产物 / 串下一阶段）。  
> 约束：遵守 [`docs/skill/guide.md`](./guide.md) 的 Skill‑First 边界；遵守 [`docs/sdui/protocol.md`](../sdui/protocol.md) 的 SDUI 协议。

---

## 0. 开工前：开发者先准备“初步素材”

在选型（纯 SDUI / EmbeddedWeb）之前，建议开发者先准备下面这些**初步素材**（不需要完美），Cursor 会基于它们做澄清与收敛：

1) **阶段定义（1 段话）**：本阶段做什么、输入是什么、输出产物是什么。  
2) **业务逻辑/状态机草案**（强烈建议用表格）：  
   - `state`：每个阶段状态（如 `start/upload/running/publish/done/cancelled`）  
   - `action`：每个触发动作（如 `start`, `resume_after_upload`, `publish`, `fallback_cancel`）  
   - `event`：每个动作要输出哪些事件（`dashboard.patch` / `hitl.*` / `artifact.publish`）  
3) **UI 呈现草图**（任选其一/可混合）：  
   - 纯 SDUI（Stepper/Statistic/TextArea/Button/ArtifactGrid）  
   - 本地 HTML 工作台（EmbeddedWeb + state 下发 + postMessage 上行）  
   - 外链 iframe（EmbeddedWeb 外链）  

---

## 1. 让 Cursor 基于“初步素材”做需求澄清（推荐）

让 Cursor 通过“访谈”把需求收敛成**可落地的状态机 + UI 节点清单**，再进入实现阶段。

把下面这段直接发给 Cursor（把尖括号内容替换成你自己的）：  

```text
你是我们 Skill‑First 平台的 Skill 开发助手。现在先不要写代码，也不要创建文件。

请你用 8-12 个问题（分组提问、每次 1-2 个关键问题即可）来澄清我这个“阶段 Skill”的需求，并最终产出：
1) 业务目标（3-5 句）
2) 输入/输出定义（输入来源、校验规则、产物清单与预览方式）
3) 状态机表（state/action/触发条件/输出事件）
4) UI 方案（选型：纯 SDUI / 本地 HTML 工作台 / 外链 iframe；并给出 SDUI 节点树草案，含稳定 id）
5) 最小可运行 MVP 范围（第一周能交付的最小闭环）

我的阶段背景（尽量简短）：
- 阶段名称：<stage4_delivery>
- 阶段定义：<...>
- 状态机草案：<...>
- UI 草图：<...>
```

> 产出物会在下一步直接喂给“实现指令模板”，用于生成 `module.json` / `dashboard.json` / `driver.py`。

---

## 2. 基于澄清结果做选型与准备输入材料

把 Cursor 的澄清产出整理成 3 样“输入材料”（后续实现会用到）：

1) **阶段定义（1 段话）**：本阶段做什么、输入是什么、输出产物是什么。  
2) **状态机表**：`state/action/触发条件/输出事件（dashboard.patch / hitl.* / artifact.publish）`  
3) **UI 节点清单**：选型（纯 SDUI / 本地 HTML 工作台 / 外链 iframe）+ SDUI 节点树草案（稳定 `id`）

---

## 3. 选一个 starter 当骨架（不要从空文件开始）

在仓库根 `skill-starters/` 选一个最接近你的阶段的 starter：  

- **本地 HTML 工作台型**：`skill-starters/stage-starter-local-html/`  
- **外链 iframe 型**：`skill-starters/stage-starter-external-web/`  
- **纯 SDUI 型**：`skill-starters/stage-starter-native-sdui/`

把 starter 目录复制到本机：`~/.nanobot/workspace/skills/`，并把目录名改成你的 skill 名（例如 `stage4_delivery`）。

---

## 4. 在 Cursor 里对 AI 的“实现指令模板”（建议照抄）

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

这条指令的目标是：**让 AI 先把骨架跑通**，而不是一次性写完全部业务（业务细节在后续迭代中补齐）。

---

## 5. 让 AI 分三轮交付（每轮都可运行/可验证）

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

## 6. EmbeddedWeb（本地 HTML 工作台）专项 SOP

如果你的阶段是“本地 HTML 工作台型”，建议把这段要求加进对 AI 的指令：  

- `dashboard.json` 的 `EmbeddedWeb.src` 使用：  
  `/api/file?path=workspace/skills/<skill>/ui/<page>.html`  
- driver 用 `dashboard.patch` merge `EmbeddedWeb.state` 下发状态（JSON）  
- HTML 内用 `window.parent.postMessage({ type: \"skill_web_intent\", payload: { action, data } }, \"*\")` 上行事件  

---

## 7. 常见踩坑（让 AI 避免）

- **模块挂载失败**：`module.json.dataFile` 不等于 `skills/<skill>/data/dashboard.json`  
- **Patch 不生效/串台**：节点没 `id` 或 `docId/syntheticPath` 不一致  
- **把业务逻辑写进平台**：违反 Skill‑First（见 [`docs/skill/guide.md`](./guide.md)）  
- **用 Patch 改结构**：Patch M1 不允许改 `children/tabs`，只能 merge 叶子字段（见 [`docs/sdui/protocol.md`](../sdui/protocol.md)）  

