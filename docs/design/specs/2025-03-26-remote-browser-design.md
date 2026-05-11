# Remote Browser 设计规格书

**状态:** Approved  
**日期:** 2025-03-26  

---

## 1. 目标与范围

在 Nanobot AGUI 右侧 Preview 面板实现基于 WebSocket 的"云端浏览器"。后端运行 Playwright，通过 WebSocket 截帧推流到前端；前端用户的点击、滚动等操作实时反馈到后端，实现人机接管。

---

## 2. 架构决策（ADR）

| ID | 决策 | 内容 |
|----|------|------|
| B1 | 传输协议 | **WebSocket**（aiohttp 原生支持），前端直连 `ws://127.0.0.1:8765/api/browser`，绕过 Next.js HTTP rewrite（WS 升级不经过 Next.js rewrite）|
| B2 | 会话隔离 | 每个 WebSocket 连接调用 `browser.new_context()` 创建独立无痕上下文，断开时 `await context.close()` 彻底销毁 Cookie/Storage/缓存，避免跨会话状态污染 |
| B3 | 视口 | 固定 `width=1280, height=800`，在 `new_context()` 时通过 `viewport` 参数设置 |
| B4 | 截帧频率 | 5 FPS（每 0.2s），JPEG quality=50，base64 编码后通过 WS 发送 |
| B5 | 依赖策略 | Playwright 作为 `[browser]` 可选依赖，运行时动态 import；缺失时 WS 返回友好错误后关闭连接 |
| B6 | URL 控制 | URL 完全由 Agent 驱动（初始 URL 通过 WS 查询参数传入）；前端仅显示只读地址栏，实时展示 `page.url` |
| B7 | 激活方式 | Agent 输出 `[实时浏览](browser://https://example.com)` Markdown 链接，前端识别 `browser://` 前缀，在 PreviewPanel 渲染 `RemoteBrowser` 组件 |
| B8 | WS URL 转换 | `http://` → `ws://`，`https://` → `wss://`，确保 HTTPS 环境不降级 |

---

## 3. 系统架构

```
Browser (Next.js :3000)
  └─ PreviewPanel.tsx
       └─ RemoteBrowser.tsx ──── ws://127.0.0.1:8765/api/browser?url=... ────►
                                                                              │
                                                                   aiohttp (:8765)
                                                                   handle_browser()
                                                                              │
                                                                   BrowserSession
                                                                   ├─ playwright (lazy)
                                                                   ├─ browser (global singleton)
                                                                   ├─ context (per-WS, 无痕)
                                                                   └─ page (per-WS)
```

---

## 4. WebSocket 消息协议

### 4.1 Server → Client

| type | 字段 | 说明 |
|------|------|------|
| `frame` | `data: str`, `url: str` | base64 JPEG 截帧 + 当前页面 URL |
| `error` | `message: str` | 错误描述（如 playwright 未安装）|

### 4.2 Client → Server

| action | 额外字段 | 说明 |
|--------|----------|------|
| `browser_interaction` type=`click` | `x_percent: float`, `y_percent: float` | 百分比坐标（已校正 object-contain 黑边）|
| `browser_interaction` type=`scroll` | `deltaY: float` | 滚轮增量 |

---

## 5. 坐标精确计算（object-contain 黑边校正）

视口固定 1280×800，aspect ratio = 1.6。

```
containerRatio = rect.width / rect.height

if containerRatio > 1.6:
    # 左右黑边（pillarbox）
    renderW = rect.height * 1.6
    renderH = rect.height
    imgLeft = (rect.width - renderW) / 2
    imgTop  = 0
else:
    # 上下黑边（letterbox）
    renderW = rect.width
    renderH = rect.width / 1.6
    imgLeft = 0
    imgTop  = (rect.height - renderH) / 2

x_percent = (relX - imgLeft) / renderW
y_percent = (relY - imgTop)  / renderH
```

点击在黑边区域时静默忽略。

---

## 6. 后端文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `nanobot/web/browser_session.py` | 新增 | BrowserSession 类：start/screenshot/click/scroll/close |
| `nanobot/web/routes.py` | 修改 | 新增 `handle_browser` WebSocket handler + 路由 |
| `pyproject.toml` | 修改 | 新增 `[browser]` optional dep: playwright>=1.40.0 |
| `nanobot/templates/TOOLS.md` | 修改 | 新增 browser:// 链接格式说明 |

## 7. 前端文件变更

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `frontend/lib/previewKind.ts` | 修改 | 新增 `"browser"` kind，匹配 `browser://` 前缀 |
| `frontend/lib/browserWsUrl.ts` | 新增 | `buildBrowserWsUrl()` http→ws / https→wss 转换 |
| `frontend/components/RemoteBrowser.tsx` | 新增 | 完整远程浏览器组件 |
| `frontend/components/PreviewPanel.tsx` | 修改 | 识别 browser kind，渲染 RemoteBrowser |

---

## 8. System Prompt 联动

在 `nanobot/templates/TOOLS.md` 中添加：

> 当你需要向用户展示网页操作过程时，请输出格式为 `[实时浏览](browser://目标网址)` 的 Markdown 链接，用户点击后将在右侧面板打开实时浏览器视图。
