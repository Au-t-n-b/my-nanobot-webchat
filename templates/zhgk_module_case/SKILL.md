---
description: 智慧工勘模块案例样板 - 从 zhgk 旧技能提炼业务主线，并通过模块 runtime 演示 HITL 选择、资料上传和大盘同步
---

# zhgk_module_case

这个模块案例面向智慧工勘团队：它把 `zhgk-scene-filter`、`zhgk-survey-build`、`zhgk-report-gen`、`zhgk-report-distribute` 四段旧技能中的核心业务主线，迁移成一个更适合在 nanobot 上复制扩展的模块样板。

## 目标

- 模块开始前先打开右侧大盘
- 在左侧会话里用 HITL 完成勘测场景选择
- 通过 FilePicker 上传 BOQ / 勘测资料包
- 让右侧的当前进展、黄金指标、产物总结随着执行实时更新，并通过 partial patch 呈现流式推进
- 把 `C:\Users\华为\.nanobot\task_progress.json` 对应的项目层进度放进“项目总览”，与模块大盘分层展示
- 在 finish 阶段产出一份迁移说明，帮助业务同事按自己的模块继续改造

## action 顺序

| action | 说明 |
|--------|------|
| `guide` | 打开模块大盘并下发启动卡片 |
| `start` | 预热指标，准备进入勘测场景选择 |
| `choose_strategy` | 下发勘测场景 ChoiceCard |
| `upload_evidence` | 下发资料上传 FilePicker |
| `after_upload` | 上传完成后刷新总结区，准备生成迁移说明 |
| `finish` | 生成 `智慧工勘模块迁移说明.md` 并挂载到产物区 |
| `cancel` | 取消并清理会话状态 |

## 业务提炼

- 场景过滤：保留“制冷方式 / 勘测场景”的入口决策价值，但在案例中先聚焦为可复制的场景选择卡片。
- 勘测汇总：保留“资料包入库后推进数据完整度”的节奏，方便后续接真实脚本。
- 报告生成：保留“评估 + 风险 + 正式报告”的目标，先在案例里汇总成迁移说明产物。
- 审批分发：在 summary 中明确这是最后一段业务逻辑，为后续真实审批节点接入预留位置。

## 给业务同事的约定

- 模块层大盘负责 `stepper-main`、黄金指标和产物区，不直接承载项目级总进度。
- 项目层总览负责汇总 `task_progress.json`，后续可以增加跨模块指标、项目阶段甘特或总览图表。
- 若要自定义图形，可以替换大盘里的可视化节点，但不要改掉稳定节点 id。

更多说明见 [flow.md](references/flow.md)。
