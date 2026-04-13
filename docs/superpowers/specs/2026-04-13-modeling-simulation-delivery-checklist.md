# 建模仿真大盘交付清单

## 交付内容

- `modeling_simulation_workbench/`
  - 当前运行中的 workspace skill 副本
  - 包含 `module.json`、`data/dashboard.json`、`SKILL.md`、`references/flow.md`
- 本交付清单

## 模块说明

- 模块 ID：`modeling_simulation_workbench`
- 当前 flow：`simulation_workflow`
- 当前主流程：
  - `guide`
  - `upload_bundle`
  - `upload_bundle_complete`
  - `device_confirm`
  - `create_device`
  - `topo_confirm`
  - `finish`
- 当前嵌入页地址：
  - `http://100.102.191.17/access.html?v=2.19.9`

## 给接收同事的使用说明

1. 将 `modeling_simulation_workbench` 放到本机 workspace 的 `skills/` 目录下。
2. 确认 `module.json` 中的 `flow` 为 `simulation_workflow`。
3. 重启当前 AGUI 或开发服务后，再进入“建模仿真模块”。
4. 如果页面仍显示旧流程，优先检查本机是否还在读取旧的 workspace 副本。

## 当前版本特性

- 已切换为建模仿真专属 flow，不再复用 `intelligent_analysis_workbench`
- 项目总览步骤为：
  - `BOQ提取`
  - `设备确认`
  - `创建设备`
  - `拓扑确认`
  - `拓扑连接`
- completed 状态下允许建模仿真模块重新触发 guide

## 验证结论

- 前端相关测试已通过
- 后端关键路径已完成冒烟验证：
  - `guide`
  - `upload_bundle_complete`
  - `finish`

