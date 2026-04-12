# modeling_simulation_workbench · 流程说明

与 `intelligent_analysis_workbench` **共用** `_flow_intelligent_analysis_workbench`，区别仅在于：

- `module.json` 中 `metricsPresentation: "embedded_web"`；
- 大盘 JSON 中黄金指标节点 id 固定为 `embedded-bilibili-golden`，类型为 `EmbeddedWeb`。

后端在 `guide` / 并行阶段 / `finish` 等节点仍会调用「指标」Patch，但会合并到 **EmbeddedWeb.state.metrics**（吞吐、质量、风险、完成度等），不再更新圆环/柱状图节点。

若需恢复图表形态，删除 `metricsPresentation` 字段（或改为非 `embedded_web`），并把 `dashboard.json` 改回 `Row` + `DonutChart` + `BarChart` 的模板结构即可。
