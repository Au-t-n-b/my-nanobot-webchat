# modeling_simulation_workbench · 流程说明

本模块使用独立的 `_flow_simulation_workflow`，只服务于 `modeling_simulation_workbench`。

## action 序列

| action | 作用 | 下一步 |
|---|---|---|
| `guide` | 重置会话，初始化 stepper/summary/embedded metrics，并展示“开始建模仿真”引导卡 | `upload_bundle` |
| `upload_bundle` | 下发真实 FilePicker，要求上传 BOQ 与建模资料包 | `upload_bundle_complete` |
| `upload_bundle_complete` | 合并上传结果，刷新 `uploaded-files`，展示设备清单预览说明 | `device_confirm` |
| `device_confirm` | 展示设备确认引导卡，等待用户确认设备清单 | `create_device` |
| `create_device` | 创建设备模型，并以流式 Patch 更新进度到拓扑确认前 | `topo_confirm` |
| `topo_confirm` | 展示拓扑确认说明，等待用户执行拓扑连接 | `finish` |
| `finish` | 完成拓扑连接，挂载报告产物，写入 task progress，清理会话状态 | 完成 |
| `cancel` | 清理会话状态并重置项目总览进度 | 结束 |

## 嵌入网页与指标

- `module.json` 中 `metricsPresentation: "embedded_web"`；
- 大盘 JSON 中黄金指标节点 id 固定为 `embedded-modeling-access`，类型为 `EmbeddedWeb`，默认 `src` 为 `http://100.102.191.17/access.html?v=2.19.9`；
- 后端在各阶段调用指标 Patch 时，会合并到 **EmbeddedWeb.state.metrics**（吞吐、质量、风险、完成度等），不再更新圆环/柱状图节点。

若需恢复图表形态，删除 `metricsPresentation` 字段（或改为非 `embedded_web`），并把 `dashboard.json` 改回 `Row` + `DonutChart` + `BarChart` 的模板结构即可。
