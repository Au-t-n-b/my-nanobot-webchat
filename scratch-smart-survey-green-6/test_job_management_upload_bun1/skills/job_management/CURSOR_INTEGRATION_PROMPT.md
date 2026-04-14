# Cursor 集成提示词：将已有 Skills 融入「作业管理」大盘

把下面整段复制到 Cursor 的 **Agent / Chat** 中作为首条消息（或保存为项目规则 `.cursor/rules` 的参考），按需替换 `{占位符}`。

---

## 系统上下文（粘贴给 Cursor）

```text
你正在 nanobot 仓库中开发。目标：把团队已有的 3 个「作业管理」相关 Skills 接入官方「作业管理大盘」模块（moduleId: job_management），实现：
1）从项目总览进入大盘后，按阶段逐步执行既有 Skill 逻辑；
2）每完成一阶段，调用 module_skill_runtime 推进 action，并用 SkillUiDataPatch 同步更新同一套 dashboard（Stepper、黄金指标、摘要文案、产物区）。

约束与事实：
- 模块配置与模板路径：`<skills_root>/job_management/`，核心文件为 module.json（flow: job_management）、data/dashboard.json、SKILL.md。
- 后端流程在 `nanobot/web/module_skill_runtime.py` 的 `_flow_job_management`：关键 action 为
  guide → upload_bundle → upload_bundle_complete → confirm_planning_schedule → confirm_engineering_schedule → confirm_cluster_schedule → finish。
- 前端通过工具 `module_skill_runtime`（或会话内 chat_card_intent）触发上述 action；大盘节点通过稳定 id 合并更新，禁止随意删除或改名以下 id：
  stepper-main, chart-donut, chart-bar, summary-text, uploaded-files, artifacts, chart-schedule-placeholder（若保留）。
- 项目总览任务进度由 module.json 的 taskProgress.tasks 与 actionMapping 驱动，与 _flow_job_management 内 _set_project_progress_and_emit 一致；新增或改名 action 时必须同时改 module.json 与 Python 分支。
- 同事已有 3 个 Skills，请映射到三阶段排期：
  - 规划设计排期 ↔ confirm_planning_schedule 之前/之中执行 Skill A
  - 工程安装排期 ↔ confirm_engineering_schedule ↔ Skill B
  - 集群联调排期 ↔ confirm_cluster_schedule ↔ Skill C
  文件上传阶段沿用 job_bundle 与 upload_bundle_complete。

请按以下步骤工作，并在修改前用 codebase_search / grep 阅读现有 _flow_job_management 与 templates/job_management。
```

---

## 任务指令（粘贴给 Cursor）

```text
【任务】集成已有 3 个 Skills 到 job_management 大盘

1. 盘点：列出 3 个 Skill 的目录名、入口（SKILL.md 描述）、是否已有 module.json / 自定义 action。若仅为「文档型 Skill」，约定由助手在对话中调用的工具名或步骤。

2. 映射：写一张表 {阶段, 大盘 action, 对应 Skill, 输入依赖（如上传路径 state.uploads）}。

3. 选实现策略（二选一或混合）：
   - A. 轻量：在 `skills/job_management/SKILL.md` 中写清编排——每个 confirm_* 前助手必须先完成对应 Skill 的检查清单，再调用 module_skill_runtime 推进；大盘仅通过既有 Patch 更新。
   - B. 深度：在 `_flow_job_management` 的 confirm_* 分支中，在 patch 大盘之前或之后 `await` 调用子逻辑（例如 `run_module_action(module_id=子模块, action=...)`、HTTP、或项目内 Python 函数），失败则 emit_guidance 报错且不推进 Stepper。

4. 若选 B：在 `module.json` 增加可配置字段（如 phaseHooks 或 childModuleIds），并在 `_flow_job_management` 读取；保持向后兼容（缺省行为与当前仓库一致）。

5. 大盘更新：任何阶段结果需反映到 dashboard 时，使用 SkillUiPatchPusher / 与现有代码相同的节点 id 合并 DonutChart、BarChart、Text、ArtifactGrid；不要新建第二份 dashboard docId，除非明确拆分产品需求。

6. 验证：本地启动前后端，走通 guide → 上传 → 三次确认 → finish；检查项目总览进度与 Stepper 一致。

7. 交付：简短说明同事如何复制 skills 目录、是否需拉取指定 commit 的 nanobot；列出你改动的文件路径。

请从步骤 1 开始，修改代码时遵循仓库既有风格，单步提交逻辑清晰的 commit。
```

---

## 使用说明（给人看的）

| 步骤 | 做法 |
|------|------|
| 1 | 将本文件与 `job_management` 文件夹一并解压到 skills 目录。 |
| 2 | 克隆/拉取包含 `job_management` 流程的 nanobot 仓库。 |
| 3 | 在 Cursor 打开 nanobot 工程，新建 Chat，先粘贴「系统上下文」，再粘贴「任务指令」。 |
| 4 | 把 `{占位符}` 换成你们真实的 3 个 Skill 名称与路径说明（可在任务指令里加一句附录）。 |
| 5 | 若希望长期生效，可将「系统上下文」精简后写入 `.cursor/rules/xxx.mdc`。 |

---

## 可选附录（自行替换后附在任务指令后）

```text
【附录 · 我方 3 个 Skill 概况】
- Skill 1 名称：________  路径：________  负责阶段：规划设计排期
- Skill 2 名称：________  路径：________  负责阶段：工程安装排期
- Skill 3 名称：________  路径：________  负责阶段：集群联调排期
- 上传材料目录约定：skills/job_management/input
```

---

文档版本：与 nanobot `job_management` 初版流程一致；若仓库中 action 名变更，请以 `templates/job_management/references/flow.md` 为准。
