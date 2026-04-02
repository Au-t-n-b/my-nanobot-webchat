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
```

---

## 常见问题

**Q：`npm run setup` 报找不到 Python / Node？**  
A：先安装 Python 3.11+ 与 Node LTS，并确保在终端中 `python`/`python3` 与 `node` 可用。

**Q：前端能开但配置保存失败？**  
A：确认 AGUI 已启动（`8765` 可访问），且 `NEXT_PUBLIC_API_BASE` 指向正确后端地址。

**Q：只想单独启动后端或前端？**  
A：后端：`python -m nanobot agui --port 8765`；前端：`cd frontend && npm run dev`。

---

## 上游与致谢

- 核心框架：**[nanobot](https://github.com/HKUDS/nanobot)**（MIT）  
- 原项目完整 README 已备份为 [`docs/legacy-nanobot-readme.md`](./docs/legacy-nanobot-readme.md)。

---

## 许可证

与上游一致，见 [LICENSE](./LICENSE)。
