# 项目引导（project_guide）

---
name: project_guide
description: 由主 Agent 按本文件在冷启动时向用户做阶段引导；冷启不依赖 Skill-First driver。
version: 0.2.0
tags: [guide, cold-start, agent]
---

## 部署位置

- 技能目录应位于与后端 `get_skills_root()` 一致的路径，例如：  
  `%USERPROFILE%\.nanobot\workspace\skills\project_guide\`  
- 本文件相对该目录为 `SKILL.md`；在 Agent 工作区中可读路径多为 **`skills/project_guide/SKILL.md`**（工作区根为 `~/.nanobot/workspace` 时）。

## 冷启动（Cold start / Agent）

**触发方式**：前端 Workbench 在会话首次就绪时，**静默**向主对话插入一条 `user` 轮（不在界面展示用户气泡，见仓库 `buildProjectGuideColdStartUserPrompt()`），由 **nanobot 主 Agent** 执行本轮；**助手**气泡会展示流式与最终引导。

**你（模型）必须**：

1. 使用 `read_file` 读取本技能文档内容（先尝试 `skills/project_guide/SKILL.md`；若不存在，用 `list_dir` 在工作区根下查找 `skills` 与 `project_guide`）。
2. 根据**上文任务指令**与**下文「对用户的引导要求」**，用**中文**输出 1～3 句，面向用户、口语化、不要复述 [系统任务-冷启动] 的原文。
3. 仅在**本文或系统说明允许**的范围内使用工具；**不得编造**未读到的项目状态、文件内容或阶段进度；若读不到 `SKILL.md`，如实简洁说明，并建议检查技能是否已部署到本机 `.nanobot/workspace/skills`。
4. 不要与「Skill-First 大盘 HITL」混为一谈；冷启的交付物是**左栏/对话中的自然语言引导**；若需后续切模块/大盘，在回复中**建议**用户如何操作，除非文档要求调用其它工具。

**对用户的引导要求（可随项目迭代在下方增删）**：

- 简要说明：当前以阶段化流程推进，你可从流程条或总览上查看进度。
- 点出 1 条**下一步建议**（如「可先在某某模块补全某资料」），具体以你从工作区/任务元数据**实际读到**的信息为准；读不到则提示用户联系管理员或从总览开始。

## 与 `runtime/driver.py` 的关系

- 冷启**不**以 `skill_runtime_start` 为主路径；`runtime/driver.py` 仅可保留为兼容旧按钮/无 LLM 的极轻量逻辑（可为空实现）。

## 给同事的交接

- 在「对用户的引导要求」中补充业务规则、工具白名单、与 Stepper/模块 id 的对应表。
- 改文案后**无需**改前端冷启常量，除非调整触发句式或要增加显式元数据。
