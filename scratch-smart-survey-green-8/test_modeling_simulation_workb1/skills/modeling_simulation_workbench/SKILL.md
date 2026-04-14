description: 建模仿真模块大盘 — 使用 simulation_workflow，黄金指标区嵌入建模仿真访问页
---

# modeling_simulation_workbench

基于独立的 **`simulation_workflow`**，通过 `module.json` 中 `metricsPresentation: "embedded_web"` 将原 Donut/Bar 黄金指标替换为 **EmbeddedWeb**（建模仿真访问页嵌入）。

## 与智能分析工作台的区别

| 项 | 说明 |
|----|------|
| `flow` | 独立为 `simulation_workflow`，不再复用 `intelligent_analysis_workbench` 的 action 序列 |
| `metricsPresentation` | `embedded_web`：Patch 只更新 `embedded-modeling-access` 的 `state`，不再写 `chart-donut` / `chart-bar` |
| `data/dashboard.json` | 黄金指标区块为 `EmbeddedWeb`，默认 `src`：`http://100.102.191.17/access.html?v=2.19.9`；`embedSandbox: false` 便于内网业务页嵌入 |
| `taskProgress` | 项目总览步骤改为 `BOQ提取 → 设备确认 → 创建设备 → 拓扑确认 → 拓扑连接` |
| `caseTemplate` | 建模仿真场景选项、指标中文名、报告文件名 |

## 替换嵌入网页

编辑 `data/dashboard.json` 中：

- `EmbeddedWeb.id`：须与后端一致，保持 `embedded-modeling-access`（若你从旧模板升级，请把原 `embedded-bilibili-golden` 改为该 id）
- `EmbeddedWeb.src`：默认已为内网建模仿真访问页，可按环境替换为完整 URL
- `state.metrics`：保留给 runtime Patch 写入吞吐、质量、风险等指标

## action 顺序

`guide` → `upload_bundle` → `upload_bundle_complete` → `device_confirm` → `create_device` → `topo_confirm` → `finish`

详见 [references/flow.md](references/flow.md)。

## 接入 workspace

将本目录复制到 `~/.nanobot/workspace/skills/modeling_simulation_workbench/`（或你的工作区 `skills/` 下），重启 AGUI 后在项目总览进入 **建模仿真模块**。
