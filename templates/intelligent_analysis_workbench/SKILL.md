---
description: 智能分析工作台 - 面向团队的全能力演示模块，展示项目级引导、HITL、上传、多阶段分析与大盘联动
---

# intelligent_analysis_workbench

这是团队最终参考案例模块，不绑定具体业务，用来展示当前 nanobot 已具备的完整模块能力组合。

## 目标

- 进入或新建会话时，先在项目总览看到“智能分析工作台”的项目阶段
- 通过项目阶段引导用户进入右侧大盘
- 在左侧会话内完成 HITL 目标选择与文件上传
- 上传后显示结构化预览卡片
- 在右侧大盘中流式展示进展、指标和阶段结论
- 通过“并行分析 + 串行汇总”生成最终结论与产物

## action 顺序

| action | 说明 |
|--------|------|
| `guide` | 模块说明与启动引导 |
| `select_goal` | HITL 选择分析目标 |
| `upload_bundle` | 下发上传卡片 |
| `upload_bundle_complete` | 收集上传结果，展示已上传文件胶囊，并等待“继续上传 / 开始分析” |
| `run_parallel_skills` | 并行推进分析阶段 |
| `synthesize_result` | 汇总结论与建议 |
| `finish` | 生成最终产物并挂载到产物区 |
| `cancel` | 清理会话状态 |

## 约定

- 项目层进度由 `task_progress.json` 驱动
- 模块层细节由 dashboard patch 驱动
- 稳定节点 id：`stepper-main`、`chart-donut`、`chart-bar`、`summary-text`、`uploaded-files`、`artifacts`

## 模块开发者重点可配置项

- `module.json > uploads[]`
  - 定义上传用途、允许文件类型、是否多选、落盘目录 `save_relative_dir`
- `module.json > taskProgress`
  - 定义项目总览里该模块的阶段列表，以及 action 到阶段完成状态的映射
- `module.json > caseTemplate.strategyOptions`
  - 定义 HITL 选择项
- `module.json > caseTemplate.metricLabels`
  - 定义黄金指标名称
- `data/dashboard.json`
  - 可调整进展、指标、总结区的具体节点内容，但不要改掉稳定节点 id

## 最小接入原则

- 平台负责能力：上传、预览、会话卡片、Patch、task_progress 自动同步
- 模块负责内容：业务 flow、HITL 文案、上传路径、指标内容、结论文案
- 若模块需要多个 skill，可在 `run_parallel_skills` / `synthesize_result` 这类 action 中自行实现串行、并行或混合编排

更多说明见 [flow.md](references/flow.md)。
