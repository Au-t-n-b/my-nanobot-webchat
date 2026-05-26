# 模块案例最终版设计

**目标**

把 `zhgk_module_case` 打磨成一版可交付给业务同事直接参考的最终案例，覆盖：
- 模块启动前自动打开大盘
- 会话内 HITL 选择与文件上传
- 右侧大盘实时展示 `当前进展 / 黄金指标 / 产物总结`
- 后续支持多模块并行时的“项目总览”

**设计原则**

1. 模块大盘和项目总览分层。
2. 模块执行进展与项目汇总进展使用同一套状态语义，但不强耦合到同一个组件。
3. 运行时更新优先走增量 Patch，而不是依赖重载 `dashboard.json`。
4. `zhgk_module_case` 既要保留智慧工勘业务主线，又要抽象出可复制的模块骨架。

**架构**

1. 模块层
`nanobot/web/module_skill_runtime.py` 负责模块案例的引导、HITL 选择、文件上传、流式步骤推进、指标更新和产物挂载。

2. 大盘层
`SkillUiWrapper` 持有模块 dashboard 文档，模块运行期只通过 `SkillUiDataPatch` 更新：
- `stepper-main`
- `chart-donut`
- `chart-bar`
- `summary-text`
- `artifacts`

3. 项目总览层
`/api/task-status` 负责把 `task_progress.json` 归一化为前端使用的项目总览数据，并补充模块活跃态摘要，供 `ProjectOverview` 展示。

**状态模型**

1. 模块 Stepper 只使用 `waiting / running / done / error`。
2. 项目总览模块卡片使用 `pending / running / completed`。
3. 模块运行中通过 `ModuleSessionFocus` 决定右侧当前高亮模块，通过 `/api/task-status` 决定项目层汇总状态。

**实时更新策略**

当前“闪一下就更新”是因为多数阶段只发最终 merge。最终版改为每个关键阶段拆成多次 Patch：
- 阶段开始：Stepper 置为 `running`
- 中间处理：`summary-text`、图表、detail 明细使用多次增量更新
- 阶段稳定：发送非 partial patch 收敛到最终态

对于需要体现流式感的节点，Patch 会带 `isPartial=true`，结束时再发稳定 patch。

**项目总览策略**

项目总览不再只是“哪些模块活跃”，而是同时展示：
- 当前项目整体完成度
- 来自 `task_progress.json` 的模块步骤进度
- 当前活跃模块
- 后续可扩展的黄金指标摘要

顶部原有 `TaskProgressBar` 的核心数据迁移到 `ProjectOverview`，顶部保留轻量状态或逐步弱化。

**zhgk 模块案例定义**

保留智慧工勘四段业务主线：
- 场景过滤
- 勘测汇总
- 报告生成
- 审批分发

但对外暴露为统一模块骨架：
- `guide`
- `start`
- `choose_strategy`
- `upload_evidence`
- `after_upload`
- `finish`

**测试策略**

1. 运行时测试
验证 `zhgk_module_case` 在关键 action 上发出正确的 Stepper 状态和流式 Patch。

2. 项目总览测试
验证 `/api/task-status` 能把默认进度和文件进度转成前端所需结构，并补充模块汇总信息。

3. 前端行为测试
优先覆盖数据转换和渲染协议，不做大范围 UI 快照。

**交付结果**

最终交付包含：
- 一版稳定可演示的 `zhgk_module_case`
- 一套可复制的模板约定
- 一层面向多模块的项目总览进度承接
