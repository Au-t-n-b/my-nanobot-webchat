---
name: smart_survey_workbench
description: 智慧工勘模块大盘，使用 smart_survey_workflow 驱动真实 GongKanSkill liveskill
---

# smart_survey_workbench

本模块保留 nanobot 标准大盘，后端执行 liveskill 中的真实智慧工勘流程，并在审批前暂停等待人工确认。

## 接入 workspace

将本目录复制到 `~/.nanobot/workspace/skills/smart_survey_workbench/`，并将同事的业务 skill 复制到
`~/.nanobot/workspace/skills/gongkan_skill/`。重启 AGUI 后进入 **智慧工勘模块**。
