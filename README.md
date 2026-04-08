<div align="center">

# 🦞 交付claw（Jiaofu Claw）

**基于 [nanobot](https://github.com/HKUDS/nanobot) AGUI 的本地开发与演示工作台**  
Agent 对话、配置中心、预览分屏、技能与远程资产等能力开箱即用。

[![Python](https://img.shields.io/badge/python-≥3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

</div>

---

## 这是什么

**交付claw** 在本仓库中聚焦于：**一条命令拉起 Python AGUI 后端 + Next.js 前端**，在浏览器内完成模型提供商、API Key、常用模型与技能工作流的配置与演示。底层能力与上游 **nanobot** 保持一致；完整上游说明与更新日志见仓库内 [`docs/legacy-nanobot-readme.md`](./docs/legacy-nanobot-readme.md)。

---

## 环境要求

| 依赖 | 说明 |
|------|------|
| **Python** | 3.11 及以上（建议 3.11+） |
| **Node.js** | LTS（用于前端与根目录脚本） |
| **Git** | 克隆本仓库 |

---

## 三步上手

在**仓库根目录**（与 `pyproject.toml` 同级）执行：

### 1. 克隆代码

```bash
git clone <你的仓库地址>
cd nanobot
```

### 2. 一键安装依赖

任选其一（**首次克隆后可直接执行**，无需先在根目录执行 `npm install`）：

```bash
npm run setup
```

或手动：

- **Windows**：`powershell -ExecutionPolicy Bypass -File scripts/setup.ps1`
- **macOS / Linux**：`bash scripts/setup.sh`

脚本会依次：用 pip **可编辑安装**本仓库的 `nanobot`、在 `frontend/` 执行 `npm ci`、安装根目录 `npm` 依赖（含 `concurrently`），并在不存在时从 `frontend/.env.local.example` 复制出 `frontend/.env.local`。

### 3. 启动前后端（一条命令）

```bash
npm run dev
```

- **前端**：默认 <http://localhost:3000>  
- **AGUI 后端**：默认 <http://127.0.0.1:8765>  

停止：在终端按 `Ctrl+C`（会同时结束两个进程）。

---

## 首次配置模型

1. 浏览器打开前端页面，点击右上角 **配置中心**（齿轮旁入口以实际 UI 为准）。  
2. 选择提供商、填写 **API Key**、必要时填写 **API Base**，设置默认模型与常用模型列表后 **保存**。  
3. 配置会写入用户目录下的 **`~/.nanobot/config.json`**（Windows 一般为 `C:\Users\<用户名>\.nanobot\config.json`），并支持热加载。

**说明**：不要把真实 Key 提交到 Git；每位同事在本机各自配置。

---

## 环境变量（前端）

复制自 `frontend/.env.local.example` 的 `frontend/.env.local` 中常用项：

| 变量 | 含义 |
|------|------|
| `NEXT_PUBLIC_API_BASE` | Python AGUI 地址，默认 `http://127.0.0.1:8765` |
| `NEXT_PUBLIC_AGUI_DIRECT` | 设为 `1` 时浏览器直连后端 API（需后端 CORS 允许） |

若前后端不同机或端口变更，请同步修改 `NEXT_PUBLIC_API_BASE`。

---

## 仓库结构（节选）

```
nanobot/
  nanobot/          # Python 包（Agent、通道、AGUI aiohttp 等）
  frontend/         # Next.js 前端（AGUI 界面）
  scripts/            # setup.ps1 / setup.sh / setup.cjs
  package.json        # 根目录：npm run setup / npm run dev
  pyproject.toml
  docs/
    legacy-nanobot-readme.md   # 原 nanobot 英文长 README 备份
    sdui-protocol-spec.md      # SDUI 协议说明
    sdui-v2-schema.json        # SDUI JSON Schema（v2）
    sdui-v3-schema.json        # SDUI JSON Schema（v3，含 Patch / Chart 等）
    claw-skill-dev-manual-v2.0.md
    claw-skill-dev-manual-v3.0.md
```

---

## SDUI v3 与 Skill UI 实时补丁（概要）

- **SkillUiDataPatch**：后端在对话 SSE 中推送 `SkillUiDataPatch` 事件，前端按 `syntheticPath`（与 `[RENDER_UI](skill-ui://SduiView?dataFile=…)` 一致）将 **SduiPatch** 合并进当前文档，右栏 SDUI 可实时更新而无需整页刷新。
- **E2E 工具**：`nanobot/agent/tools/test_sdui_v3.py` 中的 `run_asset_scan` 会写入基线 `test-scan.json`，再分段推送补丁模拟扫描进度；结束后将 **最终 100% 状态写回** 同一文件，避免磁盘长期停留在基线。
- **相关代码**：`nanobot/web/skill_ui_patch.py`（补丁载荷与推送）、`nanobot/web/routes.py` / `nanobot/agent/loop.py`（SSE 发射）；前端见 `frontend/lib/sdui.ts`、`frontend/components/SkillUiWrapper.tsx` 等。

更细的协议与 Skill 开发约定见 `docs/sdui-protocol-spec.md` 与 `docs/claw-skill-dev-manual-v3.0.md`。

---

## 近期变更摘要（前端 / 后端 / 文档）

以下为与本仓库近期提交相关的能力与修复说明（便于 Code Review 与排查问题）：

| 类别 | 说明 |
|------|------|
| **流式对话与 SSE** | `useAgentChat` 使用 `messagesRef` 构造请求体，避免将 `messages` 放入 `sendMessage` 依赖导致流式输出时回调频繁变化；`SkillUiDataPatch` 状态更新使用 `startTransition` 降低与主渲染的嵌套冲突。 |
| **Skill UI 面板** | `SkillUiWrapper` 在 `setBaseDoc` 的 updater 中不再同步调用 `setData`，改为 `queueMicrotask` 延迟同步，减轻「Maximum update depth exceeded」风险；`PreviewPanel` 向 `FilePreviewBody` 正确传入 `skillUiPatchEvent`。 |
| **路径与预览** | 归一化被误截断的 `i://…`（恢复为 `skill-ui://`）；`dataFile` 为 `workspace/…` 且 404 时尝试去掉一层 `workspace/`；`openFilePreview` 入口统一归一化 synthetic 路径。 |
| **扫描结束不回退 0%** | 仅 SSE 补丁更新内存、磁盘仍为基线时，若在 Agent 结束处无条件 `loadData()` 会从磁盘拉回基线导致界面「清 0」。现若本会话已应用过任意 patch，则 Agent 结束时不再强制 reload；`run_asset_scan` 结束时另将最终文档写回 `test-scan.json`。 |
| **文档与 Schema** | 新增/更新 v3 Schema、Claw Skill 开发手册 v3、协议文档等，与 SDUI v3 能力对齐。 |

---

## 常见问题

**Q：`npm run setup` 报找不到 Python / Node？**  
A：先安装 Python 3.11+ 与 Node LTS，并确保在终端中 `python`/`python3` 与 `node` 可用。

**Q：前端能开但配置保存失败？**  
A：确认 AGUI 已启动（`8765` 可访问），且 `NEXT_PUBLIC_API_BASE` 指向正确后端地址。

**Q：只想单独启动后端或前端？**  
A：后端：`python -m nanobot agui --port 8765`；前端：`cd frontend && npm run dev`。

**Q：Windows 上 `npm run setup` 报 ParserError、中文乱码（如 `[浜や粯claw]`）？**  
A：仓库中的 `scripts/setup.ps1` 已保存为 **UTF-8 with BOM**，供 **Windows PowerShell 5.1** 正确识别中文。若你本地改动了该文件，请仍用「UTF-8 带 BOM」保存，或改用 **PowerShell 7**（`pwsh`）执行。请勿将 `setup.ps1` 另存为 UTF-8 无 BOM，否则在简体中文系统上可能被误判编码导致解析失败。

**Q：`npm run setup` 里 Python 报 `File "<string>", line 1` / SyntaxError？**  
A：**Windows PowerShell 5.1** 把参数传给 `python.exe` 时，对「外层单引号 + 内层双引号」的引号规则与 PowerShell 7 不一致，可能把传给 `python -c` 的代码弄坏。当前脚本已改为在 **`-c` 的 Python 代码中不使用双引号**（例如用 `chr(46)` 表示点号），避免该问题。若你自行修改 `setup.ps1` 中的 `python -c`，请避免在 PS 5.1 下混用上述引号组合。

---

## 上游与致谢

- 核心框架：**[nanobot](https://github.com/HKUDS/nanobot)**（MIT）  
- 原项目完整 README 已备份为 [`docs/legacy-nanobot-readme.md`](./docs/legacy-nanobot-readme.md)。

---

## 许可证

与上游一致，见 [LICENSE](./LICENSE)。
