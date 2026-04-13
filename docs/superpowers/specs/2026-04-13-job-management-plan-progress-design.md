# 作业管理模块接入 `plan_progress` 设计

## 目标

让现有 `job_management` 模块继续保留当前四段业务大盘：

1. 文件上传
2. 规划设计排期
3. 工程安装排期
4. 集群联调排期

同时在后端实际执行时，不再使用样板逻辑，而是调用工作区中的 `plan_progress` skill 作为真实业务引擎，并把执行中的阶段状态实时映射回当前大盘与项目总览。

## 现状

- 前端大盘已稳定依赖以下节点：
  - `stepper-main`
  - `chart-donut`
  - `chart-bar`
  - `summary-text`
  - `uploaded-files`
  - `artifacts`
- 后端 `job_management` flow 目前还是样板式 HITL 确认流程。
- 同事的 `plan_progress` 已复制到工作区：
  - `C:\Users\华为\.nanobot\workspace\skills\plan_progress`
- `plan_progress` 的真实执行链路是：
  - `Stage1`
  - `Stage2`
  - `Stage3`
- `plan_progress` 支持 sidecar 事件上报，核心事件由 `scripts/flow_emit.py` 与 `scripts/flow_state_writer.py` 写入 `ProjectData/RunTime/flow_events_<task>.jsonl`

## 业务映射

大盘对外仍保留四个业务阶段，但后端执行映射为：

- `文件上传`
  - 校验 `~/skills/plan_progress/input` 下是否严格存在：
    - `到货表.xlsx`
    - `人员信息表.xlsx`
  - 若缺失任意文件，则通过 HITL 引导上传缺失文件
- `规划设计排期`
  - 执行 `plan_progress/scripts/run_all_stages.py` 的 `Stage1 + Stage2`
  - 将 `s1_preplan` 与 `s2_multiround/s2_observe_demand` 映射为当前第 2 步
- `工程安装排期`
  - 承接 `Stage3` 中的 `s3_milestone + s3_schedule`
  - 映射为当前第 3 步
- `集群联调排期`
  - 承接 `Stage3` 中的 `s3_reflection + 收尾`
  - 映射为当前第 4 步

## 文件门禁

目录固定为：

- `C:\Users\华为\.nanobot\workspace\skills\plan_progress\input`

匹配规则：

- 严格要求文件名完全等于 `到货表.xlsx`
- 严格要求文件名完全等于 `人员信息表.xlsx`

行为规则：

- 两个文件都存在：允许直接进入 `规划设计排期`
- 任一文件缺失：通过 `ask_for_file` 触发 HITL 上传
- 上传完成后再次校验；两者齐备才推进到下一阶段

## 后端接入方案

推荐保留 `flow: job_management`，只替换其内部执行逻辑，不新增新的模块 flow。

新增一个 `job_management -> plan_progress` 适配层，负责：

1. 查找与校验两个输入文件
2. 组装 `plan_progress` 运行参数
3. 启动 `run_all_stages.py`
4. 读取 sidecar 进度事件
5. 把 sidecar 阶段转成：
   - `stepper-main`
   - `summary-text`
   - KPI 图表
   - `task_progress`

## 状态转译

### `plan_progress` 阶段 -> 大盘步骤

- `s1_preplan` -> `规划设计排期`
- `s2_multiround` -> `规划设计排期`
- `s2_observe_demand` -> `规划设计排期`
- `s3_milestone` -> `工程安装排期`
- `s3_schedule` -> `工程安装排期`
- `s3_reflection` -> `集群联调排期`

### 终态规则

- `Stage1/2` 完成后：第 2 步标记 `done`，第 3 步切 `running`
- `s3_milestone + s3_schedule` 完成后：第 3 步标记 `done`，第 4 步切 `running`
- `s3_reflection` 与总控完成后：第 4 步标记 `done`，进入 `finish`

## 需要修改的文件

- `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
  - 增加 `plan_progress` 目录解析、文件门禁、脚本执行、sidecar 读取和状态转译
- `D:\code\nanobot\tests\test_module_skill_runtime.py`
  - 增加 job_management 接入 `plan_progress` 的回归测试
- `D:\code\nanobot\templates\job_management\module.json`
  - 更新任务文案与 actionMapping（如需要）
- `D:\code\nanobot\templates\job_management\references\flow.md`
  - 改成真实 `plan_progress` 接入说明
- `D:\code\nanobot\nanobot\agent\context.py`
  - 补充 job_management 上传双文件与真实运行提示

## 风险与控制

- 风险：直接改写 `plan_progress` 脚本会影响同事原逻辑
  - 控制：不改它的业务脚本，只在 `job_management` 里做适配
- 风险：sidecar 事件与当前 task name 不匹配
  - 控制：运行时统一写入固定 task name，并按该文件读取
- 风险：上传文件名不规范导致阶段无法推进
  - 控制：先做严格匹配；必要时后续再扩展为模式匹配

## 验证策略

- 测试优先覆盖：
  - 缺少输入文件时会触发 HITL
  - 两个文件齐备时会进入 `规划设计排期`
  - sidecar 中不同阶段状态能正确映射到四步大盘
  - 完成后能更新项目总览与产物区

