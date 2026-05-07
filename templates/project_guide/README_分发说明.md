# project_guide 技能包（分发用）

## 安装

1. 解压为目录 **`project_guide`**，放到本机与 `get_skills_root()` 一致的位置，通常为：

   `C:\Users\<你的用户名>\.nanobot\workspace\skills\project_guide\`

   与仓库 `templates/project_guide` 同结构，须包含 `SKILL.md`、`module.json`、`data/dashboard.json`、`runtime/driver.py`（可为占位）。

2. 确保 AGUI 工作区为 `~/.nanobot/workspace` 或你自定义且与后端一致的路径，使 Agent 能 `read_file` 到 `skills/project_guide/SKILL.md`。

## 与前端的关系

- 需使用已合并 **Workbench 冷启 + `buildProjectGuideColdStartUserPrompt`** 的前端/后端；冷启会走主对话、无用户气泡、有助手气泡（`showAssistantInTranscript: true`）。

## 可编辑

- 主要改 **`SKILL.md`** 中「对用户的引导要求」与「冷启动」节的模型指令即可。
