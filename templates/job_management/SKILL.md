---
name: job-management-dashboard
description: 作业管理（模板）— Skill-First 全能力示例（HITL + SDUI + EmbeddedWeb + artifact + progress）。
---

# 作业管理大盘 · SKILL

## 目标（作为模板）

- 用一个 Skill 同时演示：
  - **HITL 三件套**：`hitl.file_request` / `hitl.choice_request` / `hitl.confirm_request`（回执走 `skill_runtime_result`）
  - **中栏 SDUI 同步**：`dashboard.patch` 更新 summary/上传文件栅格（不设顶层 Stepper；阶段以 EmbeddedWeb 工作台与 `task_progress` 为准）
  - **复杂交互 UI**：`EmbeddedWeb`（甘特拖拽）回传 `skill_runtime_resume`（静默）
  - **右栏预览**：`artifact.publish` 发布 `schedule_draft.json`
  - **进度同步**：`task_progress.sync`

## 交付物位置

将本目录复制到工作区：`<skills_root>/job_management/`（与 `module.json` 中 `dataFile` 一致）。

## 入口（Option 1：入口按钮由 dashboard 定义）

- `data/dashboard.json` 内的按钮会发 `skill_runtime_start`：
  - `action: "jm_start"`

## Driver 动作（runtime/driver.py）

- **`jm_start`**：发 `hitl.file_request`（上传资料）
- **`jm_after_upload`**：更新 `uploaded-files`（ArtifactGrid），发 `hitl.choice_request`
- **`jm_after_choice`**：发 `hitl.confirm_request`
- **`jm_init_workbench`**：进入工作台（`dashboard.patch` 注入 EmbeddedWeb state），并发布 `schedule_draft.json`
- **`jm_workbench_ui`**：工作台 UI 状态回写（`skill_runtime_resume` 触发）
- **`jm_apply_schedule_draft`**：甘特写回 JSON，并再次 `artifact.publish`

## 数据文件（RunTime）

- `ProjectData/RunTime/schedule_draft.json`：可拖拽编辑的甘特 JSON（固定路径）
- `ProjectData/RunTime/ui_state.json`：工作台 UI 状态（圆圈/虚线框等）
- `ProjectData/RunTime/uploaded_files.json`：上传回执（模板演示）
- `ProjectData/RunTime/strategy.json`：策略选择回执（模板演示）
