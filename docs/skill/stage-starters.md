# 阶段 Skill Starter（Stage Starters）

本手册面向“业务 Skill 开发者”：用于后续阶段像 **作业管理 / 智慧工勘 / 建模仿真** 一样构建 skill（含 SDUI 大盘、HITL、产物、以及 EmbeddedWeb 工作台/外链嵌入）。

## 你应该从哪里开始

- **直接复制可运行模板**：仓库根目录 `skill-starters/`（三套 starter）  
- **理解平台边界与事件契约**：[`docs/skill/guide.md`](./guide.md)  
- **理解 SDUI 协议与 Patch 约束**：[`docs/sdui/protocol.md`](../sdui/protocol.md)  
- **理解如何推送 Patch（syntheticPath/docId/revision）**：[`docs/skill/dev-manual.md`](./dev-manual.md)

---

## 三套 Starter（复制改名即可跑）

把对应 starter 目录复制到你本机：`~/.nanobot/workspace/skills/`，再把目录名改成你的阶段 skill 名称，并同步修改 `module.json` / `data/dashboard.json` 中的 `moduleId/docId/dataFile`。

### Starter-A：本地 HTML 工作台（EmbeddedWeb 同源）

- 目录：`skill-starters/stage-starter-local-html/`
- 适用：复杂编辑器/工作台/强交互视图
- 关键点：
  - `EmbeddedWeb.src` 指向：`/api/file?path=workspace/skills/<skill>/ui/*.html`
  - 通过 `EmbeddedWeb.state`（Patch merge）下发状态；通过 `postMessage` 上行 `skill_web_intent`

### Starter-B：外链 iframe（EmbeddedWeb 外链）

- 目录：`skill-starters/stage-starter-external-web/`
- 适用：嵌入外部系统（如建模仿真）
- 关键点：
  - 受 CSP / X-Frame-Options / `frame-ancestors` 影响较大
  - 必要时可在 `dashboard.json` 设置 `embedSandbox: false`（需评估安全与合规）

### Starter-C：纯 SDUI（无 HTML）

- 目录：`skill-starters/stage-starter-native-sdui/`
- 适用：轻表单 + 指标 + 产物索引的流程型阶段
- 关键点：
  - 用 `TextArea` + `Button(action.post_user_message)` 把用户输入回传给 driver
  - driver 用 `dashboard.patch` 更新节点；用 `artifact.publish` 发布产物

---

## 推荐的阶段工作流骨架（统一口径，减少返工）

建议每个阶段都按同一套路拆：

- **Stage0 初始化**：`chat.guidance` + Stepper running + 指标清零
- **Stage1 收集输入**：需要人类介入就 `hitl.*_request`（Yield/Resume，不要阻塞等待）
- **Stage2 执行与同步**：执行中用 `dashboard.patch` 更新“叶子字段”（进度/指标/提示/EmbeddedWeb.state）
- **Stage3 发布与交接**：`artifact.publish` 发布产物；必要时 `skill_runtime_start` 串到下一阶段

> Patch M1 约束：只能按 `id` merge 叶子字段，不能改 `children/tabs` 等结构字段，详见 [`docs/sdui/protocol.md`](../sdui/protocol.md)。

---

## 对照参考实现（本机技能目录）

按你的阶段类型“抄作业”：

- 本地 HTML 工作台：`~/.nanobot/workspace/skills/job_management/`
- 高频 Patch + EmbeddedWeb.state + HITL：`~/.nanobot/workspace/skills/smart_survey/`
- 外链 iframe：`~/.nanobot/workspace/skills/jmfz/`

