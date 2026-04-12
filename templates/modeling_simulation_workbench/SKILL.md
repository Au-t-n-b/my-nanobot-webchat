---
description: 建模仿真模块大盘 — 对齐智能分析工作台交付结构，黄金指标区嵌入哔哩哔哩播放器
---

# modeling_simulation_workbench

基于 `智能分析工作台_模板交付包` 的同一套 **flow**（`intelligent_analysis_workbench`），通过 `module.json` 中 `metricsPresentation: "embedded_web"` 将原 Donut/Bar 黄金指标替换为 **EmbeddedWeb**（哔哩哔哩 `player.bilibili.com` 嵌入页）。

## 与智能分析工作台的区别

| 项 | 说明 |
|----|------|
| `metricsPresentation` | `embedded_web`：Patch 只更新 `embedded-bilibili-golden` 的 `state`，不再写 `chart-donut` / `chart-bar` |
| `data/dashboard.json` | 黄金指标区块为 `EmbeddedWeb`，`embedSandbox: false` 便于视频播放 |
| `caseTemplate` | 建模仿真场景选项、指标中文名、报告文件名 |

## 替换哔哩哔哩视频

编辑 `data/dashboard.json` 中：

- `EmbeddedWeb.src`：改为 `https://player.bilibili.com/player.html?bvid=你的BV号&...`
- `state.bvid`：与 BV 号一致（便于前端或 claw-bridge 读取）

## action 顺序

与 `intelligent_analysis_workbench` 相同：`guide` → `select_goal` → `upload_bundle` → … → `finish`。

详见 [references/flow.md](references/flow.md)。

## 接入 workspace

将本目录复制到 `~/.nanobot/workspace/skills/modeling_simulation_workbench/`（或你的工作区 `skills/` 下），重启 AGUI 后在项目总览进入 **建模仿真模块**。
