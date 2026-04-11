---
name: module_skill_demo
description: 标准模块 Skill 样本（合规流程 + 大盘 Patch + HITL ChatCard）
version: "0.1"
tags: [module, sdui, demo]
---

# 模块 Skill 样本

本目录演示 **模块交付物** 形态：

- `module.json`：声明 `docId`、`dataFile`（workspace 相对路径）、`flow` 名称。
- `data/dashboard.json`：右侧 Skill-UI 大盘初始文档（含 Stepper / Statistic / ArtifactGrid 等节点 id，供 Patch 定位）。
- `references/flow.md`：给人看的流程说明（可选）。

运行时由平台工具 `module_skill_runtime` 或会话内 `chat_card_intent`（`module_action`）驱动。

## 安装

将本目录复制到技能根目录下，例如：

`%USERPROFILE%\.nanobot\workspace\skills\module_skill_demo\`

并将 `data/dashboard.json` 同步到 **工作区** 路径：

`workspace/skills/module_skill_demo/data/dashboard.json`

（与 `module.json` 中 `dataFile` 一致。）

## 流程动作（flow=demo_compliance）

| action | 说明 |
|--------|------|
| `guide` | 重置会话状态；大盘归零；下发引导 GuidanceCard |
| `start` | 初始化扫描阶段 Patch |
| `choose_standard` | 下发 ChoiceCard（`moduleId` + `nextAction`） |
| `upload_material` | 下发 FilePicker |
| `after_upload` | 上传完成（通常由前端 Fast-path 触发） |
| `finish` | 完成统计、产物胶囊（ArtifactGrid append） |
| `cancel` | 取消并清空会话状态 |
