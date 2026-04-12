# SDUI v3 目标验收套件（Goal Suite）

本套件用于验证我们最初的目标是否“端到端闭环”：

- 生成式 UI（模块大盘）可渲染
- Visual Stream：`isPartial` + `append(children/rows)` 列表生长
- 会话内交互卡片（ChatCard）可持久化、可 replace
- 交互静默同步：`sync_state` 写入 `DocManager.meta.uiState`
- replace 触发卸载时 flush-on-dispose 仍能把最后状态写回后端
- 点击产物/网页可 `open_preview` 分屏预览

## 一、准备

右侧预览打开（模块大盘）：

`skill-ui://SduiView?dataFile=workspace/skills/sdui-goal-suite/data/dashboard.json`

确认左侧聊天可正常发送消息。

## 二、运行套件

在聊天中输入类似：

“运行 SDUI Goal Suite”

或让 Agent 调用工具：

`run_sdui_goal_suite(thread_id=<当前 threadId>)`

## 三、验收点（必须全部通过）

### 1) Bootstrap 首屏与 Patch 唤醒
- 预期：右侧大盘能先显示 Skeleton/占位，然后逐步被 Patch 更新“唤醒”。

### 2) append rows 流式生长
- 预期：产物列表（DataGrid）逐条出现，带轻微生长动效；随后稳定（结束 pulse）。

### 3) ChatCard 出现与动效
- 预期：左侧聊天流中出现一张交互卡片（FilePicker + 按钮），卡片有 **250ms slide-up** 浮现动效。

### 4) 上传与状态锁定
- 操作：在卡片中上传一个小文件。
- 预期：
  - 进度条推进到 100%
  - 300ms 成功过渡后：按钮锁定（disabled）+ 绿色对勾 + 成功提示
  - 后端 `DocManager` 中 `chat:<threadId>` 的 `meta.uiState.uploads.goalSuiteUpload` 有值

### 5) replace + flush-on-dispose
- 操作：点击“模拟完成上传”按钮。
- 预期：
  - 旧卡片被 replace（卸载）
  - 新卡片“文件已收到，正在分析中…”顺滑浮现
  - 即使在点击前正在输入/上传，卸载 flush 仍应将最后 pending 状态写入 `/api/skill/state/sync`

## 四、排障提示

- AGUI 若显示 `mode=unconfigured`，说明 Provider 未配置成功，部分 tool/LLM 行为可能不可用。
- 端口被占用：换一个端口重启（如 8767）。

