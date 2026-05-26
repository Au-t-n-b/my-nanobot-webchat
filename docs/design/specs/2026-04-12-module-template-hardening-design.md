# 模块模板加固设计

**目标**

把当前 `intelligent_analysis_workbench` 从“能演示部分链路”的模板，升级成“可直接交给模块开发同事参考”的标准案例模块，重点解决三类问题：

- 上传卡片未达到 ChoiceCard 级别的主交互体验
- Dashboard Patch 仍有跳闪，缺少连续流式动画
- 项目总览、会话交互、大盘状态三条链路未完全同步

**范围**

本轮只收敛当前模板模块和平台层公共能力，不引入新的业务模块，不改登录/项目绑定模型，不重做远端中心。目标是在现有协议下，把“开发者可配置、用户可感知、演示可复用”的链路做完整。

## 一、用户体验目标

模板模块跑通后，用户应感知到以下完整体验：

1. 从项目总览进入模块时，大盘不会长时间保持灰态，系统会静默执行 `guide` 做冷启动。
2. HITL 选择后，会话中出现一个与 ChoiceCard 同级的上传卡片，支持拖拽、多文件追加、显示目标保存目录。
3. 上传成功后，会话流和右侧大盘底部都会出现“已上传文件”胶囊区，点击胶囊可在右侧分栏预览。
4. 大盘进展、柱状图、圆环图、总结文案会随着 Skill 执行持续推进，而不是“闪一下”切到下一个快照。
5. 模块执行过程中的每个关键 action 都会同步更新项目总览所依赖的 `task_progress` / `task-status`。

## 二、实现边界

平台层负责：

- 上传协议与落盘
- 会话卡片渲染
- 右侧预览打开
- Dashboard Patch 与 TaskStatus 双写同步
- 通用输入/输出胶囊组件

模块开发者负责：

- `module.json` 中的 `uploads[]`、`taskProgress`、HITL 选项、指标文案
- `dashboard.json` 中稳定节点下的内容编排
- Flow 中每个 action 对应的业务逻辑与技能串并行方式

## 三、推荐方案

### 方案 A：只修样式与动画

优点：改动小。
缺点：上传和总览同步仍然是半成品，不足以作为标准模板。

### 方案 B：只补上传链路

优点：能快速改善 HITL 体验。
缺点：大盘跳闪和总览失真仍然存在，模板仍然不完整。

### 方案 C：模板能力一次收口

优点：以当前协议为边界，同时完成上传卡片、多文件胶囊、流式更新、总览同步，能直接成为团队参考实现。
缺点：涉及前后端多个文件，需要小心控制修改范围。

**推荐：方案 C。**

## 四、架构设计

### 1. 上传链路

上传交互保留 `FilePicker` 节点类型，但把其视觉与行为升级为“UploadCard”级体验：

- 支持拖拽和点击选择
- 支持 `multiple: true`
- 支持追加上传，不在第一次成功后锁死
- 清晰展示 `saveRelativeDir`
- 每次上传成功都向模块 action 回传 `upload` 和 `uploads[]`

前端会话中的上传卡片和大盘底部的“已上传文件”都展示同一份 `uploads[]` 数据，只是呈现位置不同。

### 2. 胶囊与预览

`SduiArtifactGrid` 继续作为统一胶囊组件，`mode="input"` 用于上传文件，`mode="output"` 用于产物。输入胶囊和输出胶囊都保持点击即打开右侧预览。

### 3. 大盘流式更新

大盘仍采用 `applySduiPatch`，但从“整段快照替换”改为“稳定节点属性渐变”：

- 带 `id` 的核心节点必须保持稳定
- 柱状图只更新 `x/y/height`
- 圆环图只更新 `stroke-dasharray/stroke-dashoffset`
- Stepper 改为节点状态和局部细节变化，不依赖整块重挂载

`SkillUiWrapper` 继续接收完整 patch，但要尽量避免因为无 `id` 节点内容 hash 改变而触发 remount。

### 4. 总览与模块双写

项目总览只看 `task-status` / `task_progress`，模块大盘只看 SDUI Patch。每个关键 action 在 runtime 结束时都要执行：

1. 更新 dashboard patch
2. 更新 `task_progress`
3. 广播 `TaskStatusUpdate`

这样可以确保总览与大盘在同一 action 边界上收敛，不再出现“右侧已完成，但总览仍 0%”。

## 五、组件与文件边界

前端重点文件：

- `frontend/components/sdui/FilePicker.tsx`
- `frontend/components/sdui/SduiArtifactGrid.tsx`
- `frontend/components/SkillUiWrapper.tsx`
- `frontend/components/sdui/SduiNodeView.tsx`
- `frontend/components/sdui/SduiBarChart.tsx`
- `frontend/components/sdui/SduiDonutChart.tsx`
- `frontend/app/globals.css`
- `frontend/lib/projectOverviewStore.ts`

后端重点文件：

- `nanobot/web/mission_control.py`
- `nanobot/web/module_skill_runtime.py`
- `nanobot/web/task_progress.py`

模板文件：

- `templates/intelligent_analysis_workbench/module.json`
- `templates/intelligent_analysis_workbench/data/dashboard.json`
- `templates/intelligent_analysis_workbench/SKILL.md`

## 六、错误处理

- 当上传配置缺少 `save_relative_dir` 时，模块加载直接报错，不进入运行时。
- 当上传接口成功但未返回 `fileId` 时，前端显示明确失败状态，不推进下一 action。
- 当 patch 到达时目标节点不存在，前端忽略该 op，但保留调试日志。
- 当总览无法匹配 `task_module_id` 时，回退按 `moduleName` 匹配，确保模板模块可继续显示。

## 七、验证策略

1. 上传验证
- 单文件与多文件都可上传
- 上传后会话区与大盘区都出现输入胶囊
- 点击胶囊可打开预览

2. 动画验证
- Stepper 不再整块闪烁
- 柱状图高度连续变化
- 圆环图角度连续变化

3. 同步验证
- `guide` 后总览进入运行态
- `upload_bundle` / `run_parallel_skills` / `finish` 后总览进度同步推进
- 大盘最终态与总览最终态一致
