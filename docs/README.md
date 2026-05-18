# Docs Index（Skill-First / SDUI）

> 最后更新：2026-05-13

本目录面向三类读者提供"最短阅读路径"：

- **业务 Skill 开发者（写阶段 Skill / 大盘 / 工作台）**：从"Skill 开发者路径"开始
- **平台开发/维护者（前后端/协议/运行时）**：从"平台维护者路径"开始
- **工具开发/集成者（Agent 工具链）**：从"Agent 工具参考"开始

---

## Skill 开发者路径（同事写阶段 Skill）

> **如果你（或你身后的 AI 助手）想"开发一个 Skill"，请先读 [`docs/skill/cursor-sop.md`](./skill/cursor-sop.md) 的 Hard Gate 段。**
>
> 在完成澄清必答题（含 **UI 挂载点必答**）并取得用户明确同意前，**禁止生成任何 Skill 业务代码文件**（`module.json` / `dashboard.json` / `driver.py` / `ui/*.html` 等）。
>
> Hard Gate 是本仓库 Skill 开发流程的最高优先级硬规则；其它文档（guide / protocol / dev-manual / starters）都是它需要时引用的参考资料。

按顺序阅读：

1. **Cursor SOP（用 AI 从零构建阶段 Skill，含 Hard Gate 与流程图）** ← 入口
   - [`docs/skill/cursor-sop.md`](./skill/cursor-sop.md)

2. **阶段 Skill Starter（Hard Gate 解除后选骨架）**
   - [`docs/skill/stage-starters.md`](./skill/stage-starters.md)
   - 代码模板目录：仓库根的 `skill-starters/`

3. **Skill-First 接入规范（事件、HITL、EmbeddedWeb、边界铁律）**
   - [`docs/skill/guide.md`](./skill/guide.md)

4. **SDUI 协议（节点白名单、Action、Patch 约束）**
   - [`docs/sdui/protocol.md`](./sdui/protocol.md)

5. **实时 Patch 手册（syntheticPath/docId/revision 与推送姿势）**
   - [`docs/skill/dev-manual.md`](./skill/dev-manual.md)

你需要对照的"真实参考实现"（本机用户目录）：
`~/.nanobot/workspace/skills/{job_management,smart_survey,jmfz}`

---

## 平台维护者路径（协议/运行时/架构）

1. **Skill Runtime / async-resume 核心语义**
   - Skill 事件白名单与边界：[`docs/skill/guide.md`](./skill/guide.md)
   - 运行时与补丁：[`docs/skill/dev-manual.md`](./skill/dev-manual.md)

2. **混合模式（受控子任务）**
   - 协议：[`docs/runtime/hybrid-mode-protocol.md`](./runtime/hybrid-mode-protocol.md)
   - 治理：[`docs/runtime/hybrid-mode-governance.md`](./runtime/hybrid-mode-governance.md)

3. **SDUI 协议与 Schema**
   - 协议：[`docs/sdui/protocol.md`](./sdui/protocol.md)
   - Schema：[`docs/sdui/schema-v2.json`](./sdui/schema-v2.json)、[`docs/sdui/schema-v3.json`](./sdui/schema-v3.json)
   - 示例：[`docs/sdui/examples/`](./sdui/examples/)

4. **渠道插件（如需）**
   - [`docs/channels/plugin-guide.md`](./channels/plugin-guide.md)

---

## Agent 工具参考

Agent 工具定义在 `nanobot/agent/tools/` 目录下，通过 `AgentLoop._register_default_tools()` 注册。
所有工具均继承 `Tool` 基类，实现 `name`、`description`、`parameters`、`execute()` 四项契约。
工具配置集中在 `nanobot/config/schema.py` 的 `ToolsConfig` 中，运行时通过 `config.json` 加载。

### 默认注册工具（14 个，无条件加载）

| 工具名 | 源文件 | 说明 |
|--------|--------|------|
| `read_file` | `tools/filesystem.py` | 读取文件内容，支持 offset/limit 分页 |
| `write_file` | `tools/filesystem.py` | 写入文件，自动创建父目录 |
| `edit_file` | `tools/filesystem.py` | 文本替换编辑，支持模糊空白匹配和全量替换 |
| `list_dir` | `tools/filesystem.py` | 目录列表，支持递归和噪音目录过滤 |
| `web_search` | `tools/web.py` | 网页搜索（Brave/Tavily/DuckDuckGo 等），配置：`tools.web.search` |
| `web_fetch` | `tools/web.py` | 抓取 URL 内容并提取可读文本 |
| `analyze_site_artifacts` | `tools/site_survey.py` | 分析工勘附件（图片/Excel 等），生成结构化统计 |
| `run_asset_scan` | `tools/test_sdui_v3.py` | SDUI v3 资产扫描 E2E 测试工具 |
| `module_skill_runtime` | `tools/module_skill_runtime.py` | 运行模块 Skill：更新大盘、下发引导/选择/上传 |
| `present_choices` | `tools/choices.py` | 向用户呈现多选项并等待选择 |
| `request_user_upload` | `tools/user_upload.py` | 请求用户上传文件，支持保存路径别名和目录配置 |
| `present_fault_log_intake_card` | `tools/fault_log_intake.py` | 呈现故障诊断日志接入卡片（SDUI ChatCard） |
| `message` | `tools/message.py` | 向用户发送消息，支持附件/媒体交付 |
| `spawn` | `tools/spawn.py` | 派生子 Agent 在后台处理任务 |

### 条件注册工具（5 个，按配置/依赖启用）

| 工具名 | 源文件 | 注册条件 | 配置类 |
|--------|--------|----------|--------|
| `exec` | `tools/shell.py` | `tools.exec.enable = true`（默认开启） | `ExecToolConfig` |
| `recall_context` | `tools/recall.py` | `MessageArchiveConfig.enabled = true`（默认开启） | `MessageArchiveConfig` |
| `cron` | `tools/cron.py` | `cron_service` 实例被传入时 | 无专属配置 |
| `send_email` | `tools/email.py` | `tools.email.enable = true`（默认关闭） | `EmailToolConfig` |
| `send_welink` | `tools/welink.py` | `tools.welink.enable = true`（默认关闭） | `WelinkToolConfig` |

### 动态注册工具（MCP）

| 工具名 | 源文件 | 说明 |
|--------|--------|------|
| `mcp_<server>_<tool>` | `tools/mcp.py` | 按 `tools.mcp_servers` 配置连接 MCP 服务器后动态注册，受 `enabled_tools` 过滤 |

### 工具配置速查（`config.json` 中的 `tools` 段）

```json
{
  "tools": {
    "restrict_to_workspace": false,
    "exec": {
      "enable": true,
      "timeout": 60
    },
    "web": {
      "search": { "provider": "brave", "api_key": "", "max_results": 5 }
    },
    "email": {
      "enable": false,
      "allowed_domains": ["huawei.com"]
    },
    "welink": {
      "enable": false,
      "xiaolubanAuth": "",
      "xiaolubanUrl": "http://xiaoluban.rnd.huawei.com:80/",
      "rate_limit_per_minute": 20,
      "rate_limit_per_day": 200
    },
    "mcp_servers": {}
  }
}
```

### send_email 工具详情

通过本机 Outlook COM 接口发送邮件。Provider 抽象设计，当前实现 `OutlookSender`，可扩展 SMTP/Graph API。

**参数**：`to`(必填), `cc`, `bcc`, `subject`(必填), `body_file`, `body_html`, `body_text`, `attachments`

**安全策略**：
- 收件人（含 CC/BCC）强制域名白名单，默认仅 `@huawei.com`
- 附件和 `body_file` 路径严格限制在 workspace 内
- 正文优先级：`body_file > body_html > body_text`
- `.html`/`.htm` 文件直接作为 HTML 正文；其他格式包裹 `<pre>` 标签

### send_welink 工具详情

通过小鲁班 HTTP API 向 WeLINK 群组/个人发送消息。

**参数**：`content`, `receiver`(必填), `format`(text/table), `table_data`

**富文本能力**：
- 颜色：`<span style="color:green;">绿色</span>`
- 加粗：`<span style="font-weight:bold;">粗体</span>`
- 表格：`format="table"` + `table_data` 自动渲染（PrettyTable + Consolas 字体）
- emoji：直接嵌入 Unicode

**鉴权**：环境变量 `XIAOLUBAN_AUTH` > `config.json` 中 `tools.welink.xiaolubanAuth`
**限流**：默认 20 次/分钟、200 次/天（小鲁班官方上限 30/min、300/day）

---

## 设计与计划（Design / Plans）

如果你在做架构演进、协议变更、前端大改版等，去这里找历史设计/计划/交接材料：

- 设计稿：`docs/design/specs/`（20 篇，2025-03 至 2026-04）
- 实施计划：`docs/design/plans/`（20 篇，2025-03 至 2026-04）
- 近期计划：`docs/plans/`（2026-04 至 2026-05）
- 交接：`docs/design/handoffs/`
- 视觉规范：`docs/design/visual-spec-v1.md`（2026-05-05）

---

## 文档时效性说明

### 当前有效（11 篇核心规范）

| 文档 | 路径 | 说明 |
|------|------|------|
| 文档索引 | `docs/README.md` | 本文件 |
| Cursor SOP | `docs/skill/cursor-sop.md` | Hard Gate 流程，2026-05-12 SOP redesign 后稳定版 |
| Skill 接入协议 | `docs/skill/guide.md` | 1069 行完整规范 |
| Skill 开发手册 v3.0 | `docs/skill/dev-manual.md` | SDUI v3 实时 Patch L-S-V 范式 |
| 阶段 Starter | `docs/skill/stage-starters.md` | 三套 Starter 模板 |
| SDUI 协议 | `docs/sdui/protocol.md` | 声明式 UI 协议全文 |
| 混合模式协议 | `docs/runtime/hybrid-mode-protocol.md` | skill.agent_task_execute 事件定义 |
| 混合模式治理 | `docs/runtime/hybrid-mode-governance.md` | Skill-First vs 受控 Agent 决策树 |
| 渠道插件指南 | `docs/channels/plugin-guide.md` | 三步构建自定义渠道 |
| 视觉规范 v1 | `docs/design/visual-spec-v1.md` | 2026-05-05，Token/Elevation/SDUI 语义色 |
| SDUI 验收套件 | `docs/testing/sdui-goal-suite.md` | E2E 验收清单 |

### 迁移 Stub（6 个旧路径，仅保留跳转）

以下文件内容已迁移至新路径，旧路径仅保留一行重定向指示：

| 旧路径 | 真实路径 |
|--------|---------|
| `docs/sdui-protocol-spec.md` | `docs/sdui/protocol.md` |
| `docs/hybrid-mode-protocol.md` | `docs/runtime/hybrid-mode-protocol.md` |
| `docs/hybrid-mode-governance.md` | `docs/runtime/hybrid-mode-governance.md` |
| `docs/CHANNEL_PLUGIN_GUIDE.md` | `docs/channels/plugin-guide.md` |
| `docs/SKILL_DEVELOPER_GUIDE.md` | `docs/skill/guide.md` |
| `docs/claw-skill-dev-manual-v3.0.md` | `docs/skill/dev-manual.md` |

### 归档 / 历史参考

| 文档 | 路径 | 说明 |
|------|------|------|
| Skill 手册 v2.0 | `docs/archive/claw-skill-dev-manual-v2.0.md` | 已由 v3.0 取代 |
| 上游 README | `docs/legacy-nanobot-readme.md` | 开源 nanobot 原始 README，最新至 v0.1.4.post5（2026-03-16） |
| Stage Starters 设计稿 | `docs/archive/plans/2026-05-11-...` | 已由 `docs/skill/stage-starters.md` 取代 |
