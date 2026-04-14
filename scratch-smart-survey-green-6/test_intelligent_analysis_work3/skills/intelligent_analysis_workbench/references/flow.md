# 智能分析工作台流程

## 角色定位

这是一个“标准模块演示中心”式案例，用于向团队说明当前 nanobot 模块应该如何组合已有能力，而不是为某个单一业务定制。

## 对外展示的能力

1. 项目总览中的阶段引导
2. 会话内 HITL 目标选择
3. FilePicker 真实上传
4. 上传后结构化预览卡片
5. 右侧大盘流式动态更新
6. 并行分析阶段
7. 串行结论汇总阶段
8. 最终产物挂载与预览

## 推荐给业务同事的替换点

1. 把 `strategyOptions` 替换成自己的业务目标或决策点
2. 把 `uploads[]` 换成自己的真实资料类型与落盘目录
3. 把“并行分析”替换成自己业务里的多个分析 skill
4. 把“结论汇总”替换成真实结论生成逻辑
5. 保留项目层与模块层分层，不要把两类状态混成一套

## 平台协议锚点

- 会话 HITL / 上传统一走 `chat_card_intent -> module_action`
- 上传结果统一写入：
  - `upload`
  - `uploads[]`
- 大盘输入文件区固定节点：
  - `uploaded-files`
- 最终产物区固定节点：
  - `artifacts`
- 项目总览进度统一读取：
  - `module.json > taskProgress`

## 推荐交付给模块同事的开发顺序

1. 先复制本模板目录
2. 修改 `module.json` 中的 `moduleId`
3. 定义 `uploads[]`
4. 定义 `taskProgress`
5. 定义 HITL 选项与业务 action
6. 修改 `dashboard.json` 的指标与总结内容
7. 保留稳定节点 id，不改 patch 锚点
