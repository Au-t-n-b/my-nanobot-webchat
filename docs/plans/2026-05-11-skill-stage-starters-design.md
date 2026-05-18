# 此文档已迁移

原日期版设计稿已归档到：

- [`docs/archive/plans/2026-05-11-skill-stage-starters-design.md`](../archive/plans/2026-05-11-skill-stage-starters-design.md)

稳定入口请看：

- [`docs/skill/stage-starters.md`](../skill/stage-starters.md)

# Skill-First 阶段 Skill 设计与 UI 参考（Stage Starters）

**目标读者**：后续要像「作业管理 / 智慧工勘 / 建模仿真」一样构建“后续阶段 skill”的同事。  
**目标**：提供一套可复制的 starter（3 种形态）+ 统一的工作流/SDUI 规范，确保不同阶段 skill 能被平台稳定运行、能驱动右侧大盘、能与 HITL/产物发布形成闭环。

本仓库事实源（建议先浏览）：

- `docs/SKILL_DEVELOPER_GUIDE.md`（Skill-First 接入规范）
- `docs/sdui-protocol-spec.md`（SDUI 节点与 Patch 契约）
- `docs/claw-skill-dev-manual-v3.0.md`（Patch 推送与宿主行为）
- 参考实现：你本机技能目录 `~/.nanobot/workspace/skills/{job_management,smart_survey,jmfz}`

---

## 1. Skill 的最小契约（必须具备）

一个“面板类”（会挂载到 DashboardNavigator/右侧 SDUI 的）skill，最小需要这些文件：

```
<skill_name>/
  module.json
  data/dashboard.json
  runtime/driver.py
  ui/                 # 可选：仅当使用 EmbeddedWeb（本地 HTML）时需要
```

### 1.1 `module.json`（面板挂载与能力声明）

你至少要填好：

- **`moduleId`**：与 skill 目录名一致（建议）
- **`docId`**：该大盘文档逻辑 id（用于 Patch revision 分桶与调试）
- **`dataFile`**：必须指向 `skills/<skill_name>/data/dashboard.json`（这是宿主合成 `syntheticPath` 的关键）

参考：`~/.nanobot/workspace/skills/job_management/module.json`

### 1.2 `data/dashboard.json`（SDUI 视图基线）

这是大盘的 **基线文档**：首次挂载时由宿主读取并渲染，运行中高频变化用 Patch 叠加。

核心约束（硬规则）：

- 禁止 `className` / `style` / 任意 CSS 逃逸（见 `docs/sdui-protocol-spec.md`）
- `Stack/Row` 的 `gap` 用 **语义枚举**（`xs/sm/md/lg/xl`），不要写像素数字
- 想被 Patch 更新的节点必须有稳定 `id`

### 1.3 `runtime/driver.py`（Skill 业务真源 / 状态机）

平台会：

- 启动子进程执行 `<skill>/runtime/driver.py`
- 将一次请求（含 `intent`）JSON 写入 stdin
- driver **按行输出 JSON envelope**（NDJSON）到 stdout
- 平台只做 envelope 校验与盲转发，不解释业务

driver 输出 envelope 的 event 白名单见：

- `docs/SKILL_DEVELOPER_GUIDE.md`（章节：标准事件包括）
- 后端实现：`nanobot/web/skill_runtime_bridge.py` 的 `SUPPORTED_SKILL_RUNTIME_EVENTS`

---

## 2. 阶段工作流设计法（建议统一方法论）

建议每个阶段 skill 都按这个“可复用骨架”拆：

- **Stage 0：初始化**  
  - 输出 `chat.guidance`（告诉用户“本阶段做什么 / 需要什么输入 / 产出什么”）
  - 大盘 Stepper 置为 `running`（Patch）

- **Stage 1：收集输入（可能 HITL）**  
  - 需要文件 → 发 `hitl.file_request`，并在 payload 中明确 `requestId/resumeAction/onCancelAction`
  - 需要选择/确认 → `hitl.choice_request` / `hitl.confirm_request`

- **Stage 2：执行与产物生成**  
  - 执行过程中用 Patch 更新：指标、进度、列表、提示区
  - 完成后用 `artifact.publish` 发布产物索引（供右侧预览）

- **Stage 3：交接到下一阶段**  
  - 需要自动衔接下一阶段时，输出 `skill_runtime_start`（链式编排）
  - 或回到 `project_guide` 做全局引导（参考智慧工勘）

注意：**HITL 是 Yield/Resume**（driver 进程不要等待输入）。当需要人类介入时，发 `hitl.*_request` 后就结束本次运行；平台会在用户完成后用 `skill_runtime_result` 重新唤醒 driver（见 `docs/SKILL_DEVELOPER_GUIDE.md` 第 6 章）。

---

## 3. SDUI / UI 设计规范（同事最常踩坑的点）

### 3.1 “右侧大盘能做什么”

右侧 SDUI 是声明式 UI，适合：

- **流程**：`Stepper`、`Tabs`、阶段提示区（`Markdown/Text/Badge`）
- **指标**：`Statistic`、`GoldenMetrics`、`DonutChart/BarChart`
- **产物**：`ArtifactGrid` + `artifact.publish` + `open_preview`
- **轻表单**：`TextArea` / `DataGrid` + `Button(action.post_user_message)`
- **重交互**：`EmbeddedWeb`（本地 HTML 或外链 iframe）+ postMessage 协议

### 3.2 EmbeddedWeb 两种嵌入模式

- **本地 HTML（同源）**：`src: /api/file?path=workspace/skills/<skill>/ui/*.html`  
  - 适合：复杂编辑器/工作台  
  - 优点：同源，限制少；可通过 `state` 下发与 postMessage 上行闭环

- **外链 iframe（跨域）**：`src: https://...` 或内网 URL  
  - 注意：可能受 CSP / X-Frame-Options / sandbox 影响  
  - 必要时可设置 `embedSandbox: false`（但要评估安全面）

### 3.3 Patch（SkillUiDataPatch / dashboard.patch）M1 约束

推荐使用 `dashboard.patch`（由平台桥接为 SSE `SkillUiDataPatch`）：

- 仅支持 `target.by = "id"`  
- 仅允许 **merge 叶子字段**（例如 `Statistic.value`、`Text.content`、`EmbeddedWeb.state`）  
- **不要**用 Patch 改 `children` / `tabs` 等结构字段；结构变化走全量基线刷新

更多细节见：`docs/sdui-protocol-spec.md` 第七章。

---

## 4. 三套 Starter（已落到仓库 `skill-starters/`，复制即可跑）

> 使用方法：将对应 starter 目录复制到你本机 `~/.nanobot/workspace/skills/` 下，并把目录名改成你的阶段 skill 名称（同时按说明修改 `module.json` 与 `dashboard.json` 里的 id/docId）。

### 4.1 Starter-A：本地 HTML 工作台（EmbeddedWeb 本地）

- 目录：`skill-starters/stage-starter-local-html/`
- 特点：`EmbeddedWeb.src = /api/file?path=workspace/skills/.../ui/workbench.html`

### 4.2 Starter-B：外链 iframe（EmbeddedWeb 外链）

- 目录：`skill-starters/stage-starter-external-web/`
- 特点：`EmbeddedWeb.src = https://example.com`，演示 `embedSandbox` 取舍

### 4.3 Starter-C：纯 SDUI（无 HTML）

- 目录：`skill-starters/stage-starter-native-sdui/`
- 特点：用 `TextArea`/`DataGrid`/`Button`/`ArtifactGrid` 组成轻量闭环

---

## 5. 从现有技能“抄作业”的推荐路径

按你的阶段特性选择参考源：

- **作业管理（本地 HTML 工作台 + Stepper）**：`~/.nanobot/workspace/skills/job_management/`
- **智慧工勘（Patch 高频 + EmbeddedWeb.state + HITL）**：`~/.nanobot/workspace/skills/smart_survey/`
- **建模仿真（外链 iframe）**：`~/.nanobot/workspace/skills/jmfz/`

如果你的阶段要“接力”到下一阶段，优先参考智慧工勘 driver 里对 `skill_runtime_start` 的用法。

