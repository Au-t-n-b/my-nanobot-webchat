---
name: job-management-dashboard
description: 作业管理大盘 — 文件上传与三段排期（规划 / 工程安装 / 集群联调），与项目总览 job_management 对齐。
---

# 作业管理大盘 · SKILL

## 何时使用

- 需要在 **项目总览** 中展示「作业管理」阶段，并打开本模块大盘。
- 需要按 **文件上传 → 规划设计排期 → 工程安装排期 → 集群联调排期** 推进，并与 `task_progress.json` 同步。

## 交付物位置

将本目录复制到工作区：`<skills_root>/job_management/`（与 `module.json` 中 `dataFile` 一致）。

## 与运行时协作

- 调用工具 `module_skill_runtime`，传入 `moduleId: job_management` 与上表 `action`。
- 大盘 UI 由 `data/dashboard.json` 定义；指标更新依赖 `chart-donut` / `chart-bar` / `golden-metrics` 等节点 id（见仓库内其它模块案例）。

## 扩展建议

- 在 `confirm_*` 各步中插入真实排期校验、外部 API 或子 Skill 调用（保持 action 名或增加 `module.json` 文档说明）。
- 新增上传类型时在 `module.json` 的 `uploads` 中声明 `purpose`，并在 `module_skill_runtime` 中扩展分支（若需自定义逻辑）。
