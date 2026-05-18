# 项目总览交互甘特图设计

日期：2026-04-12

## 目标

将项目总览中的“项目阶段甘特图”从当前的简化语义条带升级为可交互、可缩放、可平移、可实时刷新的时间轴甘特图，并继续以 `C:\Users\华为\.nanobot\task_progress.json` 为真实数据源。

第一阶段范围固定为只读实时版：

- 实时读取后端归一化后的 `task_progress` 状态
- 支持年/月/周/日视图切换
- 支持拖拽平移、滚轮缩放、回到今天
- 支持 tooltip 和点击模块跳转到对应大盘
- 不开放拖拽编辑
- 不写回 `task_progress.json`
- 不做 PNG 导出

## 当前现状

- 后端已具备 `task_progress.json -> normalize_task_progress_payload()` 的归一化能力。
- 后端已提供 `GET /api/task-status`。
- SSE 已提供 `TaskStatusUpdate`，前端已在 `useAgentChat.ts` 中接收并更新 `projectOverviewStore`。
- 项目总览页面目前使用 `SduiGanttLane` 渲染简化条带，不具备真实时间轴、缩放、平移和 Frappe 交互能力。

## 方案选择

采用方案 1：双层接入。

- 在项目总览中新增专用 `ProjectGanttChart` 组件，替换当前 `SduiGanttLane` 的用法。
- 内部使用 `frappe-gantt` 作为渲染引擎。
- 保留现有 SSE 与 store 链路，不新建前端轮询或文件监听逻辑。
- 将第三方库隔离在单独宿主组件中，避免与 React 渲染机制互相污染。

不采用方案 2 的原因：继续自绘时间轴会重复造轮子，后续交互能力扩展成本过高。

不采用方案 3 的原因：当前目标是尽快把项目总览跑起来，过早平台化会扩大改造范围。

## 数据边界

第一阶段的数据边界如下：

- 前端不直接监听文件系统。
- 数据统一从现有后端接口和 SSE 进入：
  - 初始水合：`GET /api/task-status`
  - 实时更新：`TaskStatusUpdate`
- 前端继续只消费 `projectOverviewStore.taskStatus`。
- 新甘特图组件只负责将 `taskStatus.modules[]` 映射为 `frappe-gantt` 任务，不承担源数据写回职责。

这个边界保证：

- `task_progress.json` 仍是唯一真实来源
- 前后端职责保持清晰
- 实时链路不新增第二套状态脑子

## 前端组件拆分

### 1. `frontend/components/dashboard/ProjectGanttChart.tsx`

项目总览专用包装组件。

职责：

- 读取 `projectOverviewStore` 中的任务状态
- 管理视图模式、缩放值、今天定位、点击跳转行为
- 组织工具条与画布宿主

不负责：

- 直接操作 `frappe-gantt` 实例
- 编写底层推导逻辑

### 2. `frontend/components/dashboard/frappe/ProjectGanttCanvas.tsx`

Frappe 宿主组件。

职责：

- 创建和销毁 `frappe-gantt` 实例
- 在数据变化时执行 `gantt.refresh(tasks)` 而不是整棵重建
- 管控以下关键 DOM 层级：
  - `frappe-gantt-scroll-shell`
  - `frappe-gantt-host`
  - 库内部 `.gantt-container`

约束：

- 必须使用 `useRef` 保存宿主节点和实例
- 必须使用 `useEffect` 管理生命周期
- 不允许让 React 反复重建甘特图容器，否则会与 Frappe 的原生 DOM 操作冲突

### 3. `frontend/components/dashboard/frappe/GanttChartToolbar.tsx`

顶部交互工具条。

职责：

- 视图模式切换：年 / 月 / 周 / 日
- 回到今天
- 显示当前缩放比例

### 4. `frontend/lib/projectGantt/`

纯逻辑层，不与 React 直接绑定。

计划拆分：

- `taskStatusToFrappeTasks.ts`
  - 将 `taskStatus.modules[]` 映射为 Frappe 任务结构
- `frappeViewModes.ts`
  - 定义年/月/周/日视图模式
- `ganttChrome.ts`
  - 挂载月视图 bracket、今天列高亮、依赖 hover 等视觉增强
- `ganttPanZoom.ts`
  - 拖拽平移、滚轮缩放、scrollToday 行为

这种拆分是防腐层设计，目的是把第三方库与 React 状态系统隔离开，降低后续维护风险。

## 数据映射策略

### 当前问题

同事的实现基于 `start / end / duration / progress` 这样的时间轴字段，但当前 `task_progress.json` 主要只有：

- `moduleId`
- `moduleName`
- `tasks[]`
- `completed`
- `updatedAt`

因此第一阶段需要做规则推导，而不是等待后端一次性补全所有真实计划日期。

### 第一阶段映射规则

一条甘特轨道代表一个模块，而不是模块内部的多个步骤块。

模块内部步骤继续保留，但只用于：

- 计算完成率
- 计算状态
- 生成 tooltip / 侧边详情摘要

不直接堆叠进主条带正文。

### 时间轴推导规则

若后端尚未提供真实 `startedAt / endedAt`：

- `idle / pending` 模块：
  - 锚定到“当天零点 + 固定偏移”的待排区
  - 不允许每次 SSE 推来时向右漂移
- `running` 模块：
  - 起点优先取缓存的首次进入运行态时间
  - 没有缓存时可退化使用模块 `updatedAt`
  - 终点按默认工期推导
- `completed` 模块：
  - 终点优先取完成时间或最近 `updatedAt`
  - 起点按默认工期回推

### 幂等与稳定性要求

必须避免时间抖动（Date Jitter）：

- 只要模块的 `status / doneCount / totalCount` 没变，前端推导出的 `start / end` 也不能变化
- 不能在每次 SSE 到来时直接基于 `new Date()` 重算相对位置
- 所有推导时间都必须锚定在稳定参考点上

## 实时刷新与交互行为

### 实时刷新链路

继续沿用现有链路：

`task_progress.json`
-> 后端归一化
-> `GET /api/task-status`
-> SSE `TaskStatusUpdate`
-> `useAgentChat.ts`
-> `projectOverviewStore`
-> `ProjectGanttChart`

第一阶段不新增轮询逻辑。

### 刷新策略

- `ProjectGanttCanvas` 初始化一次 Frappe 实例
- 数据变化时只调用 `gantt.refresh(tasks)`
- 不反复销毁重建实例

### 支持的交互

- 年 / 月 / 周 / 日
- 鼠标拖拽平移画布
- 滚轮缩放
- 回到今天
- hover tooltip
- 点击模块条跳转到对应模块大盘

### 明确不支持

- 拖拽改日期
- 拖拽改进度
- JSON 回写
- PNG 导出

## Frappe 接入要求

### 依赖

- `frappe-gantt`
- `html2canvas` 暂不纳入第一阶段使用，但未来导出能力可复用

### 实例化要求

- 使用 `new Gantt(hostElement, payload, options)`
- 关闭库内原生视图下拉：`view_mode_select: false`
- 视图切换由 React 工具条控制

### DOM 结构要求

- 最外层：`frappe-gantt-scroll-shell`
- 中间宿主：`frappe-gantt-host`
- 内部挂载：`.gantt-container`
- 表头 `.grid-header` 需要支持 sticky 头部行为

### 样式要求

- 颜色不硬编码到 JS 中
- 使用单独的 gantt 主题 CSS 变量文件管理颜色
- 后续深浅色模式统一走 CSS 变量注入

## 后端字段与 API 策略

第一阶段不新增 API。

继续使用：

- `GET /api/task-status`
- SSE `TaskStatusUpdate`

建议后端后续可选增强以下字段，但不作为第一阶段阻塞项：

- `startedAt`
- `endedAt`
- `progressUpdatedAt`

原则：

- 有这些字段时，前端直接使用
- 没有这些字段时，前端走规则推导
- 这样旧版 `task_progress.json` 仍兼容，新版业务再渐进增强

## 实施顺序

建议按以下顺序落地：

1. 引入 `frappe-gantt`
2. 实现 `ProjectGanttCanvas`
3. 实现 `taskStatusToFrappeTasks` 与视图模式映射
4. 实现平移、缩放、回到今天
5. 在 `ProjectOverview.tsx` 中替换当前 `SduiGanttLane`
6. 接入 tooltip 与点击跳模块
7. 最后评估是否补充后端日期字段

## 风险与规避

### 风险 1：React 与 Frappe DOM 冲突

规避：

- 第三方实例只在宿主组件中存在
- React 不直接管理 Frappe 内部节点

### 风险 2：时间推导抖动

规避：

- 所有推导必须幂等
- 使用稳定时间锚点和缓存

### 风险 3：范围失控

规避：

- 第一阶段严格不做编辑、不做导出、不做回写
- 先完成“只读但实时”的项目总览交互甘特图

## 验收标准

完成后，项目总览满足以下标准：

- 页面中出现真实时间轴甘特图，不再是简化百分比条带
- 打开页面后能基于当前 `task_progress` 立即渲染
- 当后端推送新的 `TaskStatusUpdate` 时，甘特图能实时刷新
- 支持年/月/周/日切换、拖拽平移、滚轮缩放、回到今天
- 点击模块条可进入对应模块大盘
- 页面不新增明显闪烁、抖动或实例泄漏
