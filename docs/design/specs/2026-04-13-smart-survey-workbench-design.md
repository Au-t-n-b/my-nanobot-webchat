# 智慧工勘模块接入 `GongKanSkill` 设计

## 目标

新建一个独立的 `smart_survey_workbench` 模块，参考现有建模仿真与作业管理的大盘接入模式：

1. 前端保留统一的大盘壳与 Stepper/指标/产物区
2. 后端实际执行复制到工作区 liveskill 的 `GongKanSkill`
3. 执行过程中持续把真实业务进度、文件状态和产物映射回大盘
4. Stepper 严格沿用 `GongKanSkill` 原生四步，不做业务改名

## 现状

- 同事提供的真实业务 skill 位于：
  - `C:\Users\华为\Desktop\GongKanSkill`
- `GongKanSkill` 的主编排入口为：
  - `C:\Users\华为\Desktop\GongKanSkill\zhgk\SKILL.md`
- 真实业务流程已经完整定义为四步：
  - `场景筛选与底表过滤`
  - `勘测数据汇总`
  - `报告生成`
  - `审批分发`
- 进度真相源已经存在：
  - `C:\Users\华为\Desktop\GongKanSkill\ProjectData\RunTime\progress.json`
- 每步完成后由：
  - `C:\Users\华为\Desktop\GongKanSkill\tools\update_progress.py`
  更新 `smart_survey` 模块下的任务完成状态
- 视觉参考来自：
  - `C:\Users\华为\Desktop\GongKanWeb\index.html`
- 现有 nanobot 已有可复用接入模式：
  - `D:\code\nanobot\templates\modeling_simulation_workbench`
  - `D:\code\nanobot\nanobot\web\module_skill_runtime.py`

## 总体方案

推荐采用“独立模块模板 + 独立后端 flow + 工作区 liveskill + 进度转译”的接入方式。

### 模块边界

- 新增模块目录：
  - `D:\code\nanobot\templates\smart_survey_workbench`
- 新增工作区 skill 副本：
  - `C:\Users\华为\.nanobot\workspace\skills\smart_survey_workbench`
  - `C:\Users\华为\.nanobot\workspace\skills\gongkan_skill` 或等价命名的 liveskill 目录
- 新增后端 flow：
  - `_flow_smart_survey_workflow`

### 设计原则

- 不直接执行桌面目录中的 `GongKanSkill`
- 不直接把 `GongKanWeb` 整页嵌入大盘
- 不只靠 `SKILL.md` 驱动流程
- 不修改现有建模仿真和作业管理模块的 action 语义
- `progress.json` 继续作为工勘流程的业务真相源

## 业务映射

Stepper 严格使用 `GongKanSkill` 原生四步：

1. `场景筛选与底表过滤`
2. `勘测数据汇总`
3. `报告生成`
4. `审批分发`

### 真实步骤 -> 脚本映射

- Step 1
  - `python zhgk/scene-filter/scripts/scene_filter.py`
- Step 2
  - `python zhgk/survey-build/scripts/write_image_results.py`
  - `python zhgk/survey-build/scripts/generate_survey_table.py`
  - 增量更新时：
    - `python zhgk/survey-build/scripts/merge_and_rebuild.py`
- Step 3
  - `python zhgk/report-gen/scripts/generate_assessment.py`
  - `python zhgk/report-gen/scripts/generate_risk.py`
  - `python zhgk/report-gen/scripts/generate_report.py`
- Step 4-A
  - `python zhgk/report-distribute/scripts/distribute_report.py`
- Step 4-B
  - `python zhgk/report-distribute/scripts/distribute_report_4b.py`

## 后端接入方案

`module.json` 不复用建模仿真或作业管理的 flow，改为显式声明：

- `flow: "smart_survey_workflow"`

在 `D:\code\nanobot\nanobot\web\module_skill_runtime.py` 中新增专属 `_flow_smart_survey_workflow`，负责：

1. 初始化大盘状态
2. 检查 liveskill 目录与输入文件
3. 触发 HITL 上传缺失文件
4. 执行真实脚本
5. 读取 `progress.json` 与产物文件
6. 将业务阶段转译为：
   - `stepper-main`
   - 黄金指标
   - `summary-text`
   - `uploaded-files`
   - `artifacts`
   - 项目总览 `task_progress`

## Action 设计

建议暴露给大盘的 action 序列如下：

- `guide`
  - 重置会话态
  - 读取 `progress.json`
  - 初始化 Stepper、摘要、指标和文件区
- `prepare_step1`
  - 校验 Step 1 输入件
- `run_step1`
  - 执行场景筛选与底表过滤
- `prepare_step2`
  - 校验 Step 2 输入件
- `run_step2`
  - 执行图像识别写回、结果表生成或增量合并
- `prepare_step3`
  - 校验 Step 3 输入件
- `run_step3`
  - 严格按顺序执行评估、风险、报告生成
- `prepare_step4`
  - 校验分发前置条件
- `run_step4_approve`
  - 发送专家审批邮件
- `approval_pass`
  - 审批通过后发送干系人通知
- `approval_rework`
  - 返回 Step 2 或 Step 3 补数重跑
- `cancel`
  - 清理前端会话态，不清空业务文件

## 文件门禁与 HITL 策略

原则：先自动检查 liveskill 目录中的既有文件，只有缺失时才触发 HITL 上传。

### Step 1 文件门禁

必需文件：

- `ProjectData/Start/勘测问题底表.xlsx`
- `ProjectData/Start/评估项底表.xlsx`
- `ProjectData/Start/工勘常见高风险库.xlsx`
- `ProjectData/Input/BOQ*.xlsx`
- `ProjectData/Input/勘测信息预置集.docx`

行为：

- 全部存在：允许直接执行 Step 1
- 缺失任意文件：只提示上传缺失项

### Step 2 文件门禁

必需文件：

- `ProjectData/RunTime/勘测问题底表_过滤.xlsx`
- `ProjectData/Input/勘测结果.xlsx`
- `ProjectData/Start/客户确认底表.xlsx`

可选输入：

- `ProjectData/Input/勘测结果补充材料.xlsx`
- `ProjectData/Images/*`

行为：

- 缺 `勘测结果.xlsx` 或现场照片时触发 HITL
- 若补充材料存在则自动纳入本轮处理

### Step 3 文件门禁

必需文件：

- `ProjectData/Output/全量勘测结果表.xlsx`
- `ProjectData/RunTime/评估项底表_过滤.xlsx`
- `ProjectData/RunTime/project_info.json`
- `ProjectData/Start/新版项目工勘报告模板.docx`

行为：

- 以自动校验为主，通常不触发 HITL

### Step 4 文件门禁

必需文件：

- `ProjectData/Output/工勘报告.docx`
- `ProjectData/Output/全量勘测结果表.xlsx`
- `ProjectData/Output/机房满足度评估表.xlsx`
- `ProjectData/Output/风险识别结果表.xlsx`
- `ProjectData/Start/远近一体化人员信息.xlsx`

行为：

- 缺收件人名单时触发 HITL

## 大盘设计

不嵌入完整业务网页，使用标准 SDUI 组件承接，但黄金指标与信息层级参考 `GongKanWeb`。

### 布局结构

`dashboard.json` 建议包含以下区块：

1. 模块标题与说明
2. `Stepper`
3. 黄金指标区
4. 图表区
5. 告警区
6. 结果摘要区
7. 已上传文件区
8. 作业结果产物区

### 固定节点

建议保留并新增以下稳定节点 id：

- `stepper-main`
- `metric-kpi-1`
- `metric-kpi-2`
- `metric-kpi-3`
- `metric-kpi-4`
- `metric-kpi-5`
- `chart-satisfaction`
- `chart-unsatisfied`
- `alerts`
- `summary-text`
- `uploaded-files`
- `artifacts`

## 黄金指标设计

参考 `GongKanWeb` 的五张 KPI 卡，但改为工勘模块可 patch 的标准数据结构：

- `勘测完成度`
  - 来源：Step 2 后，已完成勘测项 / 总勘测项
- `遗留问题数`
  - 来源：Step 3 后，整改待办或不满足项数量
- `机房满足度`
  - 来源：Step 3 后，评估表中“满足”占比
- `风险项数量`
  - 来源：Step 3 后，风险识别结果表条数
- `数据完整率`
  - 来源：Step 2 后，非空勘测内容占比

### 图表区

- 左图：`满足度分布`
  - 来自 `机房满足度评估表.xlsx`
- 右图：`不满足项按分类统计`
  - 来自评估结果的缺陷分类聚合

### 告警区

至少支持以下告警：

- 存在待客户确认项
- 存在待补拍图片项
- 存在待补充勘测项
- 已发送专家审批，等待回执

## 结果与产物映射

### Step 1 产物

- `定制工勘表.xlsx`
- `勘测问题底表_过滤.xlsx`
- `评估项底表_过滤.xlsx`
- `工勘常见高风险库_过滤.xlsx`

### Step 2 产物

- `全量勘测结果表.xlsx`
- `待客户确认勘测项.xlsx`
- `待拍摄图片项.xlsx`
- `待补充勘测项.xlsx`
- `project_info.json`

### Step 3 产物

- `机房满足度评估表.xlsx`
- `风险识别结果表.xlsx`
- `工勘报告.docx`
- `整改待办.xlsx`

### Step 4 结果

- 专家审批邮件已发送
- 审批通过后干系人通知已发送

## 进度同步策略

工勘模块以 `progress.json` 为真相源，不另造第二套业务进度文件。

### 真相源

- `ProjectData/RunTime/progress.json`

### 模块维度

- `moduleId: smart_survey`

### 任务映射

- `zhgk-scene-filter` -> `场景筛选与底表过滤`
- `zhgk-survey-build` -> `勘测数据汇总`
- `zhgk-report-gen` -> `报告生成`
- `zhgk-report-distribute` -> `审批分发`

### 同步原则

- 用户重新进入模块时优先读取 `progress.json`
- 用户显式指定某一步时，可临时覆盖自动续跑逻辑
- Step 4-A 发出审批邮件后只标记第 4 步为 `running`
- 只有 `approval_pass` 成功后才标记第 4 步 `completed`

## 断点恢复

根据 `progress.json` 恢复当前阶段：

- 全部未完成 -> 从 Step 1 开始
- Step 1 完成 -> 从 Step 2 开始
- Step 1~2 完成 -> 从 Step 3 开始
- Step 1~3 完成 -> 从 Step 4 开始
- 全部完成 -> 提示是否重新开始

审批阶段是唯一强制暂停点，不允许自动越过专家回执直接闭环。

## 需要修改的文件

- `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
  - 新增 `_flow_smart_survey_workflow`
  - 新增路由分支
  - 增加文件门禁、脚本执行、进度转译、指标 patch
- `D:\code\nanobot\templates\smart_survey_workbench\module.json`
  - 定义模块能力、actionMapping、taskProgress 和上传策略
- `D:\code\nanobot\templates\smart_survey_workbench\data\dashboard.json`
  - 定义 Stepper、指标、图表、告警、产物区
- `D:\code\nanobot\templates\smart_survey_workbench\references\flow.md`
  - 描述真实工勘流程与 action 序列
- `D:\code\nanobot\templates\smart_survey_workbench\SKILL.md`
  - 描述模块对话入口与用户提示
- `D:\code\nanobot\nanobot\agent\context.py`
  - 补充工勘模块 action、上传策略和审批暂停语义
- `D:\code\nanobot\tests\test_module_skill_runtime.py`
  - 补充工勘模块接入回归测试

## 风险与控制

- 风险：直接修改同事原始 `GongKanSkill` 会影响其独立可用性
  - 控制：仅复制到工作区并通过适配层调用，不篡改桌面原版
- 风险：只改 `SKILL.md` 但未新增专属 flow，导致大盘 action 与真实脚本序列不匹配
  - 控制：必须新增独立 `smart_survey_workflow`
- 风险：审批流被自动完成，破坏人工确认闭环
  - 控制：Step 4 拆成 `run_step4_approve` 与 `approval_pass`
- 风险：文件缺失时直接执行脚本导致报错
  - 控制：每步执行前先做文件门禁校验，缺失即 HITL
- 风险：新模块影响现有建模仿真与作业管理
  - 控制：新增独立模板、独立 flow、独立 moduleId，不复用已有 action 名

## 验证策略

优先验证以下场景：

- 没有任何输入件时，进入模块能正确提示缺失文件
- Step 1 输入件齐备时，能成功生成四个 RunTime 文件并更新第一步状态
- Step 2 缺 `勘测结果.xlsx` 或图片时，只提示补缺失项
- Step 2 成功后，五张黄金指标中至少能生成完成度与完整率
- Step 3 必须按 Assessment -> Risk -> Report 顺序执行
- Step 3 完成后，产物区能挂载四类核心输出
- Step 4-A 后模块停在审批等待态，不会自动完成
- 用户输入“审批通过”后，Step 4-B 才执行并闭环
- 重新进入模块时，能根据 `progress.json` 断点恢复
- 建模仿真与作业管理模块行为不受影响
