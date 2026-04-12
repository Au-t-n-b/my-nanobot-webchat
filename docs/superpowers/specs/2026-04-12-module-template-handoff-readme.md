# 智能分析工作台模板交付说明

这份交付包给模块开发同事直接参考使用，目标不是让大家“从零设计一套模块框架”，而是基于平台已经提供好的协议、组件和运行时能力，只替换自己的业务内容。

## 交付包包含什么

1. `templates/intelligent_analysis_workbench`
   母模板目录，可直接复制一份作为新模块起点。

2. `2026-04-12-module-template-hardening-design.md`
   平台设计说明，讲清楚模块平台的边界、约束和推荐做法。

3. `2026-04-12-module-template-hardening.md`
   实施清单，适合开发时逐项对照。

## 同事应该怎么开始

推荐按下面顺序接入：

1. 复制模板目录 `templates/intelligent_analysis_workbench`
2. 把目录名改成自己的模块名，例如 `my_business_module`
3. 修改 `module.json`
4. 修改 `data/dashboard.json`
5. 修改 `SKILL.md`
6. 在对应 runtime flow 中补自己的业务 action

不要先改平台代码，先用模板把自己的模块跑起来。

## 模块开发者必须改的 3 个文件

### 1. `module.json`

这是模块的“协议入口”，重点改这些字段：

- `moduleId`
  模块唯一标识，目录名和这里要一致。

- `uploads[]`
  定义上传用途、文件类型、是否多选、以及落盘目录 `save_relative_dir`。
  这里配置的目录会决定真实上传文件最终保存到 workspace 的哪个位置。

- `taskProgress`
  定义项目总览中的阶段名称，以及每个 action 对应哪些阶段会自动完成。

- `caseTemplate.strategyOptions`
  定义 HITL 选项。

- `caseTemplate.metricLabels`
  定义黄金指标名称。

### 2. `data/dashboard.json`

这是右侧大盘结构。可以换内容，但不要乱改稳定节点 id。

必须保留这些稳定节点：

- `stepper-main`
- `chart-donut`
- `chart-bar`
- `summary-text`
- `uploaded-files`
- `artifacts`

原因很简单：runtime patch 会直接更新这些节点。如果改掉 id，大盘实时更新会失效。

### 3. `SKILL.md`

这是给开发者和 agent 的模块说明书。这里要写清楚：

- 模块目标
- action 顺序
- 每个 action 的职责
- 哪些步骤需要 HITL
- 哪些步骤需要上传
- 哪些 skill 串行，哪些并行

建议把自己的真实业务流程写成清晰的 action 表，不要只写大段描述。

## 平台已经帮你做好的能力

模块开发同事不需要自己重复造这些能力：

- 会话内 HITL 选择卡
- 真实文件上传
- 按 `save_relative_dir` 落盘
- 上传后会话胶囊展示
- 大盘底部 uploaded-files 胶囊展示
- 点击胶囊后右侧分栏预览
- Dashboard Patch 实时更新
- `task_progress` / 项目总览自动同步

也就是说，平台负责“基础能力和协议”，模块负责“业务内容和文案”。

## 关于真实上传

当前模板不是模拟上传，而是真实上传：

- 前端上传卡会调用 `/api/upload`
- 后端会把文件落到 `module.json > uploads[].save_relative_dir`
- 上传后文件会生成胶囊
- 胶囊点击后可以在右侧预览

例如母模板当前配置：

```json
"uploads": [
  {
    "purpose": "analysis_bundle",
    "multiple": true,
    "save_relative_dir": "skills/intelligent_analysis_workbench/input"
  }
]
```

表示文件会真实保存到：

`<workspace>/skills/intelligent_analysis_workbench/input/`

如果你的模块要上传到别的目录，只需要改 `save_relative_dir`。

## 关于 skill 串行和并行

这套模板支持三种编排方式：

- 串行
- 并行
- 混合

模块开发者不需要改平台协议，只需要在自己的 flow action 里决定：

- 是不是在某一步并发执行多个 skill
- 是不是在并发完成后做一次串行汇总

推荐做法：

- 上传和 HITL 前置在前面
- 多个分析类 skill 放在 `run_parallel_skills`
- 汇总类 skill 放在 `synthesize_result`

## 推荐给同事的最小开发规范

每个模块都按下面规则接：

1. 先复制母模板，不从空目录起步
2. 保留稳定 dashboard 节点 id
3. 所有上传都必须通过 `uploads[]` 配置，不要自己写野路子上传
4. 每个关键 action 都要同步更新 dashboard 和 task progress
5. 上传后会话和大盘都要能看到输入胶囊
6. 最终产物只放到 `artifacts`，不要和输入文件混放

## 开发完成后至少验证什么

每个模块在交付前，至少自测下面 6 项：

1. 项目总览能看到该模块阶段
2. 进入模块后能自动打开大盘
3. HITL 能正常选择
4. 文件能真实上传到配置目录
5. 上传后会话和大盘都能出现胶囊
6. 模块执行时大盘和项目总览都能同步推进

## 最后一句建议

不要把这份模板当成“演示页面”，而要把它当成“模块开发合同”。

照着合同接，模块之间才会长得统一，平台能力才能稳定复用。
