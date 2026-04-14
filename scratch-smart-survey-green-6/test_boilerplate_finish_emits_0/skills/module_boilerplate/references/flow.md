# module_boilerplate 流程说明（给同事复制改）

这个模板要解决的不是单个 demo，而是一类可复制的业务模块交付方式：

- 每个业务拆成多个模块。
- 每个模块在 nanobot 中都要有一个先打开的大盘。
- 模块内部 Skill 通过 HITL 选择和上传文件推进。
- 执行过程中，大盘上的进展、黄金指标、产物总结要实时更新。

## 目录职责

| 文件 | 说明 |
|------|------|
| `module.json` | `docId`、`dataFile`、**`flow`**；可选 **`flowOptions`** 与 **`caseTemplate`**（见下） |
| `data/dashboard.json` | 大盘 SDUI；**稳定 `id`** 供后端 `SkillUiPatchPusher.update_node` 合并字段 |

### `dataFile` 必须与 Patch `syntheticPath` 一致

`module.json` 的 **`dataFile`**（如 `workspace/skills/<your_module>/data/dashboard.json`）决定后端发出的 **`syntheticPath`**。前端 **`DashboardNavigator`** 对模块的占位 URL 为  
`skill-ui://SduiView?dataFile=workspace/skills/<moduleId>/data/dashboard.json`。  
两者**查询串必须逐字相同**，否则右栏 `SkillUiWrapper` 会丢弃 SSE Patch，**进展 Stepper / 黄金指标**看起来「永远不动」；**作业结果**若仅靠磁盘基线或聊天文案，容易误判为「只有那块在变」。

`finish` 追加产物使用 **`append` → `ArtifactGrid.artifacts`**；宿主 `applySduiPatch` 须识别该 op（与 `mission_control.add_artifact` 对齐）。
| `SKILL.md` | 模型说明：何时调用工具、各 `action` 顺序 |

### flowOptions（`module.json`）

| 字段 | 说明 |
|------|------|
| `requireEvidenceBeforeStrategy` | `true` 时：`start` 会检查 `skills/<module_id>/input/` 是否已有文件；若无则 **仅下发 FilePicker**（不经模型），上传后再进入策略 ChoiceCard。 |
| `evidenceSaveRelativeDir` | 上传落盘目录（workspace 相对路径），默认 `skills/<module_id>/input`。 |

设为 `false` 可恢复「先策略、再上传」的旧顺序。

### caseTemplate（`module.json`）

`caseTemplate` 用来承载“业务同事可先改配置、不急着改 Python”的字段：

| 字段 | 说明 |
|------|------|
| `moduleTitle` | 模块案例名称；会出现在引导文案、总结文案、交付说明中 |
| `moduleGoal` | 模块目标/案例用途说明 |
| `strategyPrompt` | 会话内策略选择卡片标题 |
| `strategyOptions` | 策略选项列表 |
| `metricLabels` | 黄金指标名称，如吞吐、质量、风险 |
| `reportLabel` | 右侧产物区展示的交付文件名称 |
| `reportFileName` | `finish` 阶段实际生成到 `output/` 的文件名 |

## 动作序列（与代码一致）

1. **`guide`** — 重置会话状态、初始化大盘、下发 **GuidanceCard**（会话内嵌按钮），并让前端先聚焦到当前模块大盘。
2. **`start`** — 推进 Stepper/黄金指标 Patch，进入选择前状态。
3. **`choose_strategy`** — 下发 **ChoiceCard**；用户选择后由前端发 `choice_selected`，进入 **`upload_evidence`**。
4. **`upload_evidence`** — 下发 **FilePicker**；上传成功后前端发 `module_action` → **`after_upload`**。
5. **`after_upload`** — 替换卡片为确认态，Patch 大盘。
6. **`finish`** — 总结文案、Stepper 完成、**ArtifactGrid** 追加真实可预览产物，并发 `ModuleSessionFocus` idle。

## 给业务模块的复制约定

1. 先复制这个目录，保持 `guide/start/choose_strategy/upload_evidence/after_upload/finish` 主干不变。
2. 把 `dashboard.json` 的三大块继续保留为：
   当前进展
   黄金指标
   产物总结
3. 图表可以自由替换成柱状图、饼图、甘特、地图或外链预览，但**节点 id 要稳定**。
4. 每进入一个关键阶段，就发一次或多次 `SkillUiDataPatch`，不要只在左侧聊天里更新文案。

## 新建自有模块三步

1. 复制本目录为 `skills_root/<your_module_id>/`。
2. 先修改 `module.json` 的 `docId`、`dataFile`、`caseTemplate`。
3. 再编辑 `dashboard.json` 布局与 `id`，最后在 Python 中按相同 `id` 发 Patch。

## 安装到本机 skills 根

默认技能根：`~/.nanobot/workspace/skills`（Windows：`%USERPROFILE%\.nanobot\workspace\skills`）。

将模板目录复制为：

`skills/module_boilerplate/`（文件夹名等于 `module_id`）。

可选：设置环境变量 `NANOBOT_AGUI_SKILLS_ROOT` 指向仓库内 `workspace/skills` 做开发联调。

## 绕过模型：会话内嵌 `chat_card_intent`（推荐排障）

若模型谎称「没有 `module_skill_runtime`」，可在输入框发送 **一段含下列 JSON 的文本**（整段以 `{` 开头最佳；前面有分隔线等杂质亦可，后端会从第一个 `{` 起解析）：

```json
{"type":"chat_card_intent","verb":"module_action","payload":{"moduleId":"module_boilerplate","action":"guide","state":{}}}
```

该路径 **不经过大模型**，直接执行 `run_module_action`。后续步骤可继续点卡片，或按需再发同类 JSON（改 `action`）。

## 清空进度（重复测试）

- 在 **模块大盘** 顶部 Tab 栏右侧点 **「清空进度」**：会再次执行 `guide`（清空 `_SESSION` 并重置 Stepper/图表等 Patch）。
- 若左侧会话里历史消息太乱，可再 **新建会话** 后重新发 `guide` 或点引导卡片。

## 前端手动验证（nanobot）

1. 将本仓库的 `templates/module_boilerplate` **整夹**复制到 `%USERPROFILE%\.nanobot\workspace\skills\module_boilerplate`（PowerShell：`Copy-Item -Recurse -Force <repo>\templates\module_boilerplate $env:USERPROFILE\.nanobot\workspace\skills\module_boilerplate`）。
2. 启动 Python AGUI 服务与 Next 前端（`frontend` 下 `npm run dev`，确保 `/api/chat` 能代理到后端）。
3. 浏览器打开应用，**新建会话**。
4. **方法二**：让助手调用 `module_skill_runtime`（`module_id`=`module_boilerplate`，`action`=`guide`）。若模型不认工具，改用上一节的 **chat_card_intent** 一行 JSON。
5. **预期**：左侧消息流出现 **内嵌引导卡片**（非系统弹窗）；中间 **DashboardNavigator** 出现 `module_boilerplate` 模块，大盘为「进展 + 黄金指标 + 作业结果」三块；悬停 Stepper 圆点可看 **细分进展**。
6. 点击「启动样板流程」→ 大盘指标变化；再让助手依次执行 `choose_strategy`、`finish`（上传步骤在用户选完策略后由 **选择卡片** 自动链到 `upload_evidence`，用户 **上传文件** 后自动进入 `after_upload`，最后助手 `finish`）。
7. **finish** 后：总结文案更新，产物区出现 **模块案例交付说明.md**，点击后 **右侧预览分屏** 打开；甘特区可点 **外链按钮** 试 `open_preview`。
