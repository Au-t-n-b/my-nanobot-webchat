# Nanobot AGUI UI Enhancements Plan (Phase 1–5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在已完成的后端 API（Phase 1 原计划 Tasks 1-7）与侧栏生态（Phase 3）基础上，全面补完 UI 蓝图的 5 个增强阶段。

**Already done — DO NOT re-implement:**
- SSE 流式聊天、HITL、选择题弹框、文件预览（原计划 Tasks 1-7）
- 技能树 API、文件索引 Tooltip、安全回收站（Phase 3 侧栏生态）
- 消息气泡左右对齐、自动滚底、Mermaid SVG 缩放
- backtick 文件名 → 可点击链接（`normalizeAssistantLinks`）
- `<a>` 点击拦截 → 右侧 PreviewPanel

---

## 进度总览

| Phase | 方向 | 状态 |
|-------|------|------|
| Phase 1 | 全局视觉、主题与响应式 | ⬜ 未开始 |
| Phase 2 | 极致聊天流交互 | ⬜ 未开始 |
| Phase 3 | 工作区侧栏生态 | ✅ **已完成** |
| Phase 4 | 多模态智能解析与分流 | 🟡 部分完成 |
| Phase 5 | 记忆体与持久化 | 🟡 部分完成（threadId 已持久，messages 未持久）|

---

## File map

| Path | Responsibility |
|------|---------------|
| `frontend/app/ThemeProvider.tsx` (new) | next-themes 三档主题封装 |
| `frontend/hooks/useTheme.ts` (new) | 主题状态 + localStorage |
| `frontend/components/ThemeToggle.tsx` (new) | 三档主题切换按钮 |
| `frontend/app/globals.css` (modify) | CSS 变量三套色板 |
| `frontend/app/layout.tsx` (modify) | 注入 ThemeProvider |
| `frontend/components/ErrorToast.tsx` (new) | 全局 Error Toast（5s 自动消失 + 重试）|
| `frontend/app/page.tsx` (modify) | 挂载 ThemeToggle / ErrorToast / SearchOverlay / 汉堡菜单 |
| `frontend/components/MessageList.tsx` (modify) | 头像 + 消息复制按钮 + 搜索高亮 |
| `frontend/components/SearchOverlay.tsx` (new) | Ctrl+F 搜索浮层 |
| `frontend/components/AgentMarkdown.tsx` (modify) | 极客代码块（语言/行数/折叠/复制）+ 路径 auto-linkify |
| `frontend/components/InlinePreviewBlock.tsx` (new) | 小文件原地展开预览（.mmd/.json/代码类）|
| `frontend/hooks/useAgentChat.ts` (modify) | messages localStorage 持久化 + 容量限流 |

---

## 🎨 Phase 1: 全局视觉、主题与响应式

### Task 1.1: 多主题持久化 (next-themes)

**Files:** `frontend/app/ThemeProvider.tsx`, `frontend/hooks/useTheme.ts`, `frontend/components/ThemeToggle.tsx`, `frontend/app/globals.css`, `frontend/app/layout.tsx`

- [ ] **1.1.1** 安装 `next-themes`：`npm install next-themes`

- [ ] **1.1.2** 创建 `app/ThemeProvider.tsx`，配置 `themes: ['dark','light','soft']`，`defaultTheme: 'dark'`，`attribute: 'data-theme'`。

- [ ] **1.1.3** 在 `globals.css` 定义三套 CSS 变量：
```css
[data-theme="dark"]  { --bg: #09090b; --fg: #f4f4f5; --panel: #18181b; --border: #27272a; }
[data-theme="light"] { --bg: #ffffff; --fg: #18181b; --panel: #f4f4f5; --border: #e4e4e7; }
[data-theme="soft"]  { --bg: #0f172a; --fg: #e2e8f0; --panel: #1e293b; --border: #334155; }
```

- [ ] **1.1.4** 更新 `layout.tsx`：根节点包裹 `<ThemeProvider>`；`<html>` 去掉硬编码 `className`。

- [ ] **1.1.5** 创建 `ThemeToggle` 组件：三个圆形按钮（`Moon / Sun / Palette` 图标），挂载到 Sidebar 底部或页面右下角。

- [ ] **1.1.6** 替换全局硬编码颜色（重点：`bg-zinc-950` → `bg-[var(--bg)]`，`border-zinc-800` → `border-[var(--border)]`，`bg-zinc-900` → `bg-[var(--panel)]`）。

- [ ] **1.1.7** 验证：切换主题 → 刷新 → 无闪烁恢复；代码块 light 模式下为浅底深字。

- [ ] **1.1.8** Lint + commit：`feat(frontend): next-themes three-way theme with CSS variables`

---

### Task 1.2: 响应式与无障碍 (A11y)

**Files:** `frontend/app/page.tsx`, `frontend/components/Sidebar.tsx`

- [ ] **1.2.1** 移动端适配：
  - 默认侧栏 `hidden md:flex`（768px 以下隐藏）
  - 页面左上角增加汉堡按钮（`Menu` 图标），点击切换 `sidebarOpen` state
  - 小屏侧栏以 `fixed inset-y-0 left-0 z-40 w-72 translate-x` 抽屉形式呈现
  - 背景蒙层 `fixed inset-0 bg-black/50 z-30`，点击关闭

- [ ] **1.2.2** 无障碍：
  - 发送按钮：`aria-label="发送消息"`
  - 关闭按钮（PreviewPanel、Modal）：`aria-label="关闭"`
  - 主题切换：`aria-label="切换主题"`
  - 技能列表：`role="list"`，每个技能 `role="listitem"`，支持 Tab + Enter 激活

- [ ] **1.2.3** Lint + commit：`feat(frontend): mobile responsive sidebar + a11y aria labels`

---

### Task 1.3: 全局错误 Toast

**Files:** `frontend/components/ErrorToast.tsx`, `frontend/app/page.tsx`

- [ ] **1.3.1** 创建 `ErrorToast` 组件：
  - Props：`message`, `onRetry?`, `onClose`
  - 样式：`fixed top-4 left-1/2 -translate-x-1/2 z-50`，动画 `animate-slide-down`
  - 5 秒 `setTimeout` 后自动调用 `onClose`
  - 包含"重试"按钮（若传入 `onRetry`）和"×"关闭按钮

- [ ] **1.3.2** 在 `page.tsx` 用 `errorToast` state 接管 `error`，替换现有的 ChatArea 内联错误显示。当 API 失败时触发 Toast；点"重试"重新调用上一次 `sendMessage`。

- [ ] **1.3.3** Lint + commit：`feat(frontend): global error toast with auto-dismiss and retry`

---

## 💬 Phase 2: 极致聊天流交互

### Task 2.1: 头像 + 消息复制按钮

**Files:** `frontend/components/MessageList.tsx`

- [ ] **2.1.1** 头像：
  - user 气泡左侧：`<User size={14} className="text-zinc-400" />` 小圆框
  - assistant 气泡左侧：`<Bot size={14} className="text-sky-400" />` 小圆框
  - 布局：`flex gap-2 items-start`，头像 `shrink-0 mt-0.5`

- [ ] **2.1.2** 消息复制按钮：
  - 在 `<li>` 上加 `group` class
  - 气泡右上角 `group-hover:opacity-100 opacity-0 transition` 的复制按钮
  - 点击 `navigator.clipboard.writeText(m.content)`，500ms 显示 `<Check>` 反馈

- [ ] **2.1.3** Lint + commit：`feat(frontend): message avatars and hover copy button`

---

### Task 2.2: 极客代码块 (Smart Foldable Code)

**Files:** `frontend/components/AgentMarkdown.tsx`

代码块 Header 规范：
```
┌─ [语言名]  [行数 lines]  ────────────  [复制] [折叠▲/展开▼] ┐
│  代码内容                                                    │
└──────────────────────────────────────────────────────────── ┘
```

- [ ] **2.2.1** 修改 `pre` renderer：改为 `FoldableCodeBlock` 客户端组件。
  - 从 `children` 中提取语言（`className="language-xxx"`）和代码文本
  - 计算行数：`text.split('\n').length`
  - 默认折叠阈值：超过 **15 行**时 `collapsed = true`

- [ ] **2.2.2** Header 组件：左侧语言 badge + 行数；右侧复制按钮 + 展开/收起 Toggle。

- [ ] **2.2.3** 折叠时内容区设 `max-h-[160px] overflow-hidden`，展开时 `max-h-none`，过渡 `transition-[max-height] duration-300`。

- [ ] **2.2.4** 亮色适配：`[data-theme="light"] pre { background: #f8f8f8; color: #1a1a1a; }`。

- [ ] **2.2.5** Lint + commit：`feat(frontend): foldable code blocks with language label, line count, and copy`

---

### Task 2.3: 会话内 Ctrl+F 搜索

**Files:** `frontend/components/SearchOverlay.tsx`, `frontend/app/page.tsx`, `frontend/components/MessageList.tsx`

- [ ] **2.3.1** 创建 `SearchOverlay` 组件：
  - Props：`query`, `onQueryChange`, `total`, `current`, `onPrev`, `onNext`, `onClose`
  - 样式：`fixed top-4 right-4 z-50 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl p-2`
  - 包含输入框 + `↑↓` 按钮 + `n/total` 计数 + `Esc` 关闭

- [ ] **2.3.2** 在 `page.tsx` 监听全局 `keydown`：`Ctrl/Cmd+F` 唤起浮层（阻止默认行为）；`Esc` 关闭。

- [ ] **2.3.3** 在 `MessageList` 接受 `searchQuery?: string`，当非空时对每条消息内容做正则分词，用 `<mark className="bg-amber-400/30 rounded text-amber-200">` 包裹命中片段。

- [ ] **2.3.4** 当前命中条目自动 `scrollIntoView({ behavior: 'smooth', block: 'center' })`，按 `↑↓` 在命中项间跳转。

- [ ] **2.3.5** Lint + commit：`feat(frontend): Ctrl+F search overlay with highlight and smooth navigation`

---

## 🗂️ Phase 3: 工作区侧栏生态

> **✅ 已在 Phase 3（2026-03-24）完全实现，跳过。**

- [x] 3.1 技能树 API 联动（GET /api/skills + 刷新 + 预览 + 打开文件夹）
- [x] 3.2 动态文件索引 + Tooltip（正则嗅探 + 文件名显示 + 全路径 title）
- [x] 3.3 安全回收站（POST /api/trash-files + 二次确认 + 部分失败保留）

---

## 📄 Phase 4: 多模态智能解析与分流

### 🟡 已完成部分
- backtick 文件名 → `/api/file?path=` 链接（`normalizeAssistantLinks`）
- `<a>` 点击拦截 → 右侧 `PreviewPanel`（所有已知扩展名）

### Task 4.1: 全局纯文本路径拦截 (Auto-Linkify)

**Files:** `frontend/components/AgentMarkdown.tsx`

- [ ] **4.1.1** 在 `normalizeAssistantLinks` 中追加一条正则，匹配**纯文本**绝对路径（Windows `C:\...` 和 Unix `/...`），将其转化为 `[basename](/api/file?path=encoded)` 链接：
```ts
// Windows: C:\path\to\file.ext  or  D:/path/to/file.ext
const WIN_PATH_RE = /(?<![`\[(])([A-Za-z]:[/\\][^\s`\])"'\n]{3,}\.(?:FILE_EXT_RE))/g;
// Unix: /home/user/... or /Users/...
const UNIX_PATH_RE = /(?<![`\[(])(\/(?:home|Users|tmp|var|opt|workspace)[^\s`\])"'\n]{3,}\.(?:FILE_EXT_RE))/g;
```
- 使用负向后瞻避免重复处理已有 Markdown 链接和 backtick 内容

- [ ] **4.1.2** 同步更新 `fileIndex.ts` 的 `extractIndexedFiles`，追加对以上两种路径格式的扫描。

- [ ] **4.1.3** Lint + commit：`feat(frontend): auto-linkify bare Windows and Unix absolute paths`

---

### Task 4.2: 链接名称美化 + 图片复制路径按钮

**Files:** `frontend/components/AgentMarkdown.tsx`, `frontend/components/PreviewPanel.tsx`

- [ ] **4.2.1** 在 `agentMarkdownComponents` 的 `a` renderer 中，当识别为文件链接时：
  - `children` 若与路径相同（全路径显示），替换为只显示 `basename`
  - 文件链接统一加 `title={fullPath}` hover 提示

- [ ] **4.2.2** 图片类型预览（`PreviewPanel.tsx` 的 `embed` image case）：在图片下方添加"复制路径"按钮，点击将 `filePath` 写入剪贴板，500ms 显示 `<Check>` 反馈。

- [ ] **4.2.3** Lint + commit：`feat(frontend): link name beautification and image copy-path button`

---

### Task 4.3: 小文件原地内嵌预览 (InlinePreviewBlock)

**Files:** `frontend/components/InlinePreviewBlock.tsx` (new), `frontend/components/AgentMarkdown.tsx`

分流规则：

| 文件类型 | 行为 |
|----------|------|
| `.html`, `.pdf`, `.docx`, `.xlsx`, `.png/jpg/gif/webp`, `.md` | → 右侧 `PreviewPanel` |
| `.mmd`, `.json`, `.yaml`, `.toml`, `.csv`, `.txt`, `.log`, `.ts/.tsx/.js/.jsx/.py/.rs/.sh` | → 原地 `InlinePreviewBlock` |

- [ ] **4.3.1** 创建 `InlinePreviewBlock` 组件：
  - Props：`path`, `onClose`
  - `fetch(/api/file?path=...)` 拿内容，按扩展名渲染（mermaid / 代码块 / JSON 格式化 / 纯文本）
  - 头部：文件名 + 展开/收起 Toggle + 关闭按钮
  - 折叠时 `max-h-[200px] overflow-hidden`，展开时 `max-h-[80vh] overflow-auto`

- [ ] **4.3.2** 在 `agentMarkdownComponents` 的 `a` renderer 中修改分流逻辑：
  - 大文件类型 → 调用 `onFileLinkClick(path)`（传给 PreviewPanel）
  - 小文件类型 → 在消息内原地插入 `<InlinePreviewBlock>`
  - 同一文件同一消息内防重复插入（`Set<string>` 去重）

- [ ] **4.3.3** Lint + commit：`feat(frontend): inline preview block for small files with fold/unfold`

---

## 💾 Phase 5: 记忆体与持久化

### 🟡 已完成部分
- `threadId` 已通过 `THREAD_STORAGE_KEY` 持久化

### Task 5.1: messages 历史状态持久化

**Files:** `frontend/hooks/useAgentChat.ts`

- [ ] **5.1.1** 在 `useAgentChat` 初始化时从 `localStorage.getItem('agui_messages')` 恢复 `messages`（JSON.parse + 类型校验，失败则 `[]`）。

- [ ] **5.1.2** `useEffect([messages])` 时将 messages 序列化写入 localStorage（仅当 `messages.length > 0`）。

- [ ] **5.1.3** `clearChat` 时同步 `localStorage.removeItem('agui_messages')`。

- [ ] **5.1.4** 验证：发送消息 → 刷新 → 消息保留；"清空当前对话" → 刷新 → 消息已清空。

---

### Task 5.2: 容量限流

**Files:** `frontend/hooks/useAgentChat.ts`

- [ ] **5.2.1** 写入 localStorage 前截断：只保留最近 **50 条**消息。

- [ ] **5.2.2** 估算总大小（`JSON.stringify(messages).length`）超过 **1.8 MB** 时，进一步从头部裁剪，直到低于阈值。

- [ ] **5.2.3** Lint + commit：`feat(frontend): messages localStorage persistence with 50-item and 1.8MB cap`

---

## 最终验收 Checklist

- [ ] 三档主题切换，刷新无闪烁，代码块 light 模式可读
- [ ] 移动端 768px 以下侧栏隐藏，汉堡菜单可呼出
- [ ] API 失败时 Toast 弹出，5 秒消失，"重试"按钮有效
- [ ] 消息气泡有头像；hover 出现复制按钮
- [ ] 代码块超 15 行默认折叠，语言 + 行数 header 正确
- [ ] `Ctrl+F` 唤起搜索，高亮正确，↑↓ 翻页，Esc 关闭
- [ ] 纯文本绝对路径自动转为可点击链接
- [ ] 文件链接只显示文件名，图片预览有"复制路径"按钮
- [ ] 小文件原地预览，大文件右侧面板，防重复插入
- [ ] 刷新保留对话，清空后刷新无内容，50条/1.8MB 截断生效

---

## 推荐执行顺序（由独立到耦合）

1. **Phase 5.1 + 5.2**（持久化）— 独立，3 步搞定
2. **Phase 2.1**（头像 + 复制按钮）— 独立，最小改动
3. **Phase 2.2**（极客代码块）— 独立
4. **Phase 1.3**（Error Toast）— 独立
5. **Phase 2.3**（Ctrl+F 搜索）— 中等复杂度
6. **Phase 4.1 + 4.2**（Auto-linkify + 名称美化）— 中等
7. **Phase 4.3**（InlinePreviewBlock）— 最复杂，依赖 4.1/4.2
8. **Phase 1.1**（主题系统）— 跨文件重构，最后做
9. **Phase 1.2**（响应式 + A11y）— 最后收尾

---

## Plan revision

- **2026-03-24:** Initial plan — consolidated from user UI blueprint (Phase 1–5), cross-referenced with current codebase to mark done/partial/pending items. Phase 3 fully done. Phase 4/5 partially done.
