# 作业管理大盘 · 模块动作

与 `flow: job_management` 对应，`module_skill_runtime` 支持的动作：

| action | 说明 |
|--------|------|
| `guide` | 进入模块，Stepper 进入「文件上传」；同步项目任务「作业待启动」。 |
| `upload_bundle` | 先严格校验 `skills/plan_progress/input` 下是否已有 `到货表.xlsx`、`人员信息表.xlsx`；若缺失则触发 HITL 上传。 |
| `upload_bundle_complete` | 再次校验双文件；校验通过后把文件回显到大盘，并进入「规划设计排期」。 |
| `confirm_planning_schedule` | 调用 `plan_progress` 的 Stage1 + Stage2，映射到大盘的「规划设计排期」。 |
| `confirm_engineering_schedule` | 调用 `plan_progress` 的 Stage3 `milestone + schedule`，映射到「工程安装排期」。 |
| `confirm_cluster_schedule` | 调用 `plan_progress` 的 Stage3 `reflection`，映射到「集群联调排期」。 |
| `finish` | 闭环：更新指标、写 `output/job_management_handover.md`、清空会话。 |
| `cancel` | 取消本次会话状态。 |

当前固定映射：

- `文件上传`：校验并上传 `到货表.xlsx`、`人员信息表.xlsx`
- `规划设计排期`：`plan_progress` 的 `Stage1 + Stage2`
- `工程安装排期`：`plan_progress` 的 `Stage3 milestone + schedule`
- `集群联调排期`：`plan_progress` 的 `Stage3 reflection + 收尾`

接入其他真实 Skill 时，优先保持同一批节点 id 不变：`stepper-main`、`chart-donut`、`chart-bar`、`summary-text`、`uploaded-files`、`artifacts`。这样后端只替换执行逻辑，大盘 Patch 契约无需重写。
