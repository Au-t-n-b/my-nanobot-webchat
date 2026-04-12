# 智慧工勘模块案例流程

## 为什么要单独迁移成模块案例

旧版 `zhgk` 是多个 skill 串联：

1. `zhgk-scene-filter`
2. `zhgk-survey-build`
3. `zhgk-report-gen`
4. `zhgk-report-distribute`
5. `zhgk-pipeline` 负责把状态翻译成 dashboard

这种结构适合强流程编排，但不利于业务团队按统一模块样板去复制。`zhgk_module_case` 的目标就是把核心主线压成一套更通用的模块骨架。

## 模块案例里的对应关系

| 旧能力 | 新模块案例中的体现 |
|--------|--------------------|
| 场景过滤 | `choose_strategy` 的勘测场景 HITL 选择 |
| BOQ / 预置集 / 勘测结果上传 | `upload_evidence` 的资料包上传 |
| pipeline dashboard | `dashboard.json` + `module_skill_runtime` 的实时 Patch |
| 评估表 / 风险表 / 工勘报告 | `finish` 阶段输出的迁移说明，可继续替换为真实产物 |

## 推荐给业务同事的扩展点

1. 把 `module.json.caseTemplate.strategyOptions` 换成自己的关键决策点。
2. 保留 `stepper-main`、`chart-donut`、`chart-bar`、`summary-text`、`artifacts` 这些稳定节点 id。
3. `after_upload` 之后建议用多次 partial patch 推进指标和总结，避免大盘只“闪一下”就完成。
4. 项目总览走 `task_progress.json` 聚合，模块大盘只负责单模块实时态，二者不要混写同一份状态。
5. 在 `finish` 中接入真实的脚本或工具，把迁移说明替换成真实业务产物。
6. 若后续要恢复更细的工勘流程，可在 `start` 到 `finish` 之间继续拆分动作，但尽量保留 “先大盘、再 HITL、再产物” 的交互原则。
