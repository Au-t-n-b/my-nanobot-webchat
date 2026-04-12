# 作业管理大盘 · 模块动作（初版）

与 `flow: job_management` 对应，`module_skill_runtime` 支持的动作：

| action | 说明 |
|--------|------|
| `guide` | 进入模块，Stepper 进入「文件上传」；同步项目任务「作业待启动」。 |
| `upload_bundle` | 请求上传 `job_bundle`；下一步为 `upload_bundle_complete`。 |
| `upload_bundle_complete` | 资料已入库；进入「规划设计排期」，需 HITL 确认。 |
| `confirm_planning_schedule` | 确认规划设计排期；进入「工程安装排期」。 |
| `confirm_engineering_schedule` | 确认工程安装排期；进入「集群联调排期」。 |
| `confirm_cluster_schedule` | 确认集群联调排期；可结束或进入 `finish`。 |
| `finish` | 闭环：更新指标、写 `output/job_management_handover.md`、清空会话。 |
| `cancel` | 取消本次会话状态。 |

同事接入自有 Skill 时：优先通过 **同一批节点 id**（`stepper-main`、`chart-donut`、`chart-bar`、`summary-text`、`uploaded-files`、`artifacts`）发 Patch，或在 `module.json` 中扩展 `capabilities` 与上传用途。
