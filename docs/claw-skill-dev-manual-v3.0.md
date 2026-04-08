# Claw Skill Development Handbook (v3.0)

**适用范围**：Nanobot / Skill UI（SDUI v2 文档 + **v3 实时 Patch**）  
**交付物**：本手册 + `docs/sdui-v2-schema.json`（文档体）+ `docs/sdui-v3-schema.json`（含 `SduiPatch` / SSE 载荷）  
**协议对齐**：`docs/sdui-protocol-spec.md` 第七章、`frontend/lib/sdui.ts`、`nanobot/web/skill_ui_patch.py`、`nanobot/agent/loop.py`（`emit_skill_ui_data_patch_event`）

---

## 第一章　这套体系解决什么问题

在 v2.0 基础上，v3.0 增加 **不整页刷新、按节点 id 局部更新** 的能力：Logic 在识别到业务结果（例如工勘产物就绪）后，通过 **`/api/chat` SSE** 推送 `SkillUiDataPatch`，右栏 `SduiView` 在 **同一 `syntheticPath`** 下应用 Patch，并用工勘大盘统一 **`docId: dashboard:gc`** + **单调 `revision`** 防止乱序回滚与多 Skill 串台。

---

## 第二章　交付物清单与目录

- **手册（本文件）**：`docs/claw-skill-dev-manual-v3.0.md`
- **文档 JSON Schema（v2 体）**：`docs/sdui-v2-schema.json`
- **Patch / SSE 契约**：`docs/sdui-v3-schema.json`（`$defs/SduiPatch`、`$defs/SkillUiDataPatchSse`）
- **协议详解**：`docs/sdui-protocol-spec.md` 第七章

---

## 第三章　L‑S‑V（Logic‑State‑View）范式（与 v2 相同）

- **Logic（Python）**：唯一允许做业务计算、识别工勘产物、决定何时推 Patch。
- **State**：单一事实源；全量基线仍可写回 `dataFile`（dashboard.json），Patch 用于高频增量。
- **View（dashboard.json）**：纯声明式；**禁止**在 JSON 里做计算；展示值由 Logic 算好再写入文档或 Patch。

---

## 第四章　SDUI v3：从 Logic 推送 Patch（标准姿势）

### 4.1 运行时如何挂上 SSE

浏览器走 **`POST /api/chat`** 时，`routes.handle_chat` 会在本轮请求内：

1. 注册 **`emit_skill_ui_patch`**（内部即 `safe_write("SkillUiDataPatch", payload)`）；
2. 通过 **`agent.set_skill_ui_patch_emitter(...)`** 写入与「工具审批」同级的 **ContextVar**；
3. 本轮结束在 `finally` 里 **`reset_skill_ui_patch_emitter`**。

因此：**只有在上述 Web 聊天链路里**，下面的 `emit_skill_ui_data_patch_event` 才会真正推到前端；CLI、单测、未绑定 emitter 时调用 **自动 no-op**，不会抛错。

### 4.2 推荐：`SkillUiPatchPusher`（一行更新节点，无需手拼 `ops`）

构造时绑定 **`syntheticPath`**（默认使用环境变量 **`NANOBOT_GC_DASHBOARD_SYNTHETIC_PATH`**，未设置则为 `skill-ui://SduiView?dataFile=workspace/dashboard.json`）与可选 **`doc_id`**（工勘大盘固定 **`dashboard:gc`**）。  
**`merge` 要求知道节点 `type`**（与 JSON 中一致），叶子字段放在 **`fields`** 里。

```python
from nanobot.web.skill_ui_patch import SkillUiPatchPusher

pusher = SkillUiPatchPusher()  # 或 SkillUiPatchPusher("skill-ui://SduiView?dataFile=workspace/dashboard.json")

await pusher.update_node(
    "stat-1",
    "Statistic",
    {"value": "95%", "color": "success"},
)
```

单次快捷函数（仍须传入 **`node_type`**）：

```python
from nanobot.web.skill_ui_patch import push_gc_dashboard_node_merge

await push_gc_dashboard_node_merge(
    "stat-1",
    "Statistic",
    {"value": "45%", "color": "warning"},
)
```

多节点同一 revision： **`await pusher.update_nodes([("a", "Text", {...}), ("b", "Badge", {...})])`**。

### 4.3 底层：`build_skill_ui_data_patch_payload` + `emit_skill_ui_data_patch_event`

需要自定义 `ops`（或调试）时再用低层 API；路径校验失败时会在服务端打 **`skill_ui_patch_build_failed | reason=invalid_synthetic_path`**。未绑定 Web SSE 时 **`emit_skill_ui_data_patch_event`** 会打 **`skill_ui_patch_emit_skipped | reason=no_sse_emitter`**（结构化日志）。

### 4.4 内置工具：`analyze_site_artifacts`

Agent 已注册 **`analyze_site_artifacts`**（`nanobot/agent/tools/site_survey.py`）：按 **`artifact_paths`** 顺序处理工作区内文件，**每处理完一个文件**即调用 **`SkillUiPatchPusher`** 更新满足度 **`Statistic`**（默认 **`stat-1`**），实现 0% → … → 100% 的跳动。可在复杂解析逻辑中替换「轻量 stat」段，保留多次 **`update_node`** 调用即可。

### 4.5 应在哪里调用（loop vs 工具）

| 位置 | 说明 |
|------|------|
| **自定义 Tool 的 `execute`（异步）** | 最直观：例如 `read_file` / 解析工勘结果成功后，在同一协程里 `await push_...()`。 |
| **Agent 循环外的任务** | 若不在 `process_direct` 的异步上下文中，emitter 未绑定，**不会推送到浏览器**；需改为由工具或经 bus 回到带 emitter 的请求内执行。 |

**不推荐**在 `loop.py` 核心循环里硬编码业务分支；应通过 **工具** 或 **独立 Python 模块** 由 Logic 显式调用，保持与 v2 相同的「Logic 层」边界。

### 4.6 与全量 `dataFile` 的关系

- **基线**：首次加载仍以 **`dataFile`** 指向的 JSON 为准。
- **增量**：高频更新用 Patch；若需「落盘持久化」，仍由 Logic 写文件，前端可在回合结束触发 `loadData` 强刷（现有行为）。

---

## 第五章　动作（Action）与交互回传（与 v2 一致）

支持 `post_user_message`、`open_preview`；图表下钻等见 `docs/sdui-protocol-spec.md`。

---

## 第六章　节点与 Schema

- **静态文档结构**：仍以 `docs/sdui-v2-schema.json` 与 v2 手册节点速查为准。
- **Patch**：`docs/sdui-v3-schema.json` 中 **`SduiPatch`** 必填 **`docId`、`revision`、`ops`**；SSE 外层见 **`SkillUiDataPatchSse`**。

---

## 第七章　宿主与调试（前端）

- **精准路由**：仅当 SSE 的 `syntheticPath` 与面板一致时应用。
- **revision**：按 `docId` 记录已应用最大值；`revision` 不大于该值则丢弃。
- **开发模式日志**：在浏览器控制台（开发构建）可查看 `[SkillUiDataPatch]` 的 **applied / discard / buffered** 日志。生产环境如需临时打开，可在控制台执行：  
  `window.__NANOBOT_DEBUG_SKILL_UI_PATCH__ = true`

---

## 附录 A　系统提示词模板（v3 增补）

在 v2 模板基础上，若 Skill 需要「大盘随工勘进度跳动」，请增加类似说明：

- 静态 `dashboard.json` 仍输出完整 **`SduiDocument`**；实时数值可由宿主通过 **Patch** 更新，节点需带稳定 **`id`**。
- Patch 由 **Python Logic** 调用 **`SkillUiPatchPusher`** 或 `build_skill_ui_data_patch_payload` 生成，**不要**在 JSON 内手写 `revision`。

---

## 附录 B　环境变量（可选）

- **`NANOBOT_GC_DASHBOARD_SYNTHETIC_PATH`**：未在代码里写死 `syntheticPath` 时，**`SkillUiPatchPusher()`** 默认使用该值（否则用内置默认 `workspace/dashboard.json` 路径）。
