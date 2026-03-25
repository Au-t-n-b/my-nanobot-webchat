📋 AGUI_REFACTOR_PLAN (Nanobot 现代化重构蓝图)
1. 核心特性对齐 (Feature Requirements)
新系统必须在 Next.js 前端 100% 实现以下 5 大核心特性：

浏览器单页三栏布局：侧栏（模型/技能/文件索引） + 主对话区 + 右侧可选的富媒体分屏预览。

POST + SSE 流式交互：一次用户发送 → 建立 SSE 连接 → 流式接收中间态（思考、工具）与最终态。

Human-in-the-loop (执行前确认)：Agent 调用敏感工具前挂起（ToolPending），前端展示卡片，等待用户点击「运行/取消」。

动态选择题模态框 (Choices Modal)：Agent 调用 present_choices 后，前端拦截 RunFinished 中的 choices 字段，弹出界面居中的 Tailwind 模态框，选完后将选项作为下一条用户消息发出。

全格式文件分屏预览：针对 /file?path=... 拦截点击，在右侧面板无缝预览 HTML iframe, PDF, 图片, Markdown (react-markdown), Mermaid 图表, Excel (xlsx 库) 和 Word (mammoth 库)。

2. Python 后端改造 (基于原生 Nanobot)
目标：将 aiohttp 服务端改造为纯 API 提供者。

2.1 API 路由定义
POST /api/chat：核心流式接口。接收 { threadId, runId, messages, humanInTheLoop }，调用 nanobot 原生的 process_direct 逻辑，返回 text/event-stream。

POST /api/approve-tool：接收 { threadId, runId, toolCallId, approved: bool }，通过触发内部挂起的 asyncio.Future 恢复 Agent 执行。

GET /api/file?path=...：文件读取。必须包含路径清洗容错（将 \ 转 /，清除 \r\n），支持绝对路径，及相对 workspace 的路径。

2.2 SSE 事件契约规范 (event: <name>\ndata: <json>\n\n)
RunStarted: { "threadId": "...", "runId": "...", "model": "..." }

StepStarted: { "stepName": "thinking|tool", "text": "..." }

TextMessageContent: { "delta": "..." }

ToolPending: { "threadId": "...", "runId": "...", "toolCallId": "...", "toolName": "...", "arguments": "{...}" } (触发前端 HITL 卡片)

RunFinished: { "threadId": "...", "choices": [{"label": "A", "value": "a"}], "message": "..." } (触发前端模态框)

3. Next.js 前端架构设计 (新建 frontend 目录)
目标：利用 React 状态机驾驭复杂的 Agent 交互。

3.1 核心状态 Hook (hooks/useAgentChat.ts)
不要使用 Vercel AI SDK。手写 fetch 请求后端的 /api/chat。

使用 ReadableStream 逐行解析 SSE 文本流，更新 messages 数组。

维护 pendingTool 状态（控制 HITL 按钮渲染）和 pendingChoices 状态（控制 Modal 渲染）。

3.2 布局与组件树 (app/page.tsx)
使用 Tailwind CSS 构建深色极简 UI (bg-zinc-950 text-zinc-100)：

<Sidebar />: 历史记录、模型切换、技能展示。

<ChatArea />:

<MessageList />: 支持渲染 marked 气泡、折叠的 StepStarted 思考日志、高亮的 ToolPending 确认卡片。

<ChatInput />: 底部固定的文本框。

<ChoicesModal />: 绝对定位/居中的遮罩层弹窗。

<PreviewPanel />: 接收 previewUrl 状态，位于右侧。

3.3 离线文件解析策略 (在 frontend 内 npm install)
当点击 Markdown 链接拦截到文件路径时，根据后缀渲染 <PreviewPanel />：

图片/PDF：直接走原生的 <img src={url} /> 或 <iframe src={url} />。

HTML：fetch 获取文本后，使用 <iframe srcDoc={content} sandbox />。

Markdown: 使用 react-markdown + remark-gfm 渲染。

Excel (.xlsx): 使用 xlsx 库解析为 JSON，渲染为 Tailwind <table>。

Word (.docx): 使用 mammoth 库转换为 HTML 字符串注入。

Mermaid: 动态调用 mermaid.render()。

4. 重构执行步骤 (Execution Steps)
(注：Cursor，请务必做完一步，等待用户确认后，再做下一步！)

[ ] Step 1: 后端 API 化改造。在 nanobot 的入口文件中，修改/新增 /api/chat 等路由。构建一套基于假数据的 SSE 测试流（生成 TextMessageContent 和 RunFinished），确保 CORS 配置允许 Next.js 本地调试跨域访问。

[ ] Step 2: 前端工程初始化。在根目录运行 npx create-next-app@latest frontend（选择 TS + Tailwind + App Router）。编写底层的 useAgentChat.ts Hook，成功连通后端的 SSE 测试流。

[ ] Step 3: 核心 UI 与三栏布局。在 Next.js 中实现深色主题的 <Sidebar>, <ChatArea>，并实现类似 ChatGPT 的消息气泡（区分 User 和 AI）。

[ ] Step 4: HITL 闭环联调。后端接入真实的 nanobot Agent Future 阻塞逻辑；前端解析 ToolPending 事件，渲染卡片并调用 /api/approve-tool 解除阻塞。

[ ] Step 5: 选择题 Modal 联调。后端拦截 present_choices 抛出 choices 数组；前端解析并弹出居中 Modal，实现点击后自动回复的闭环。

[ ] Step 6: 本地文件分屏预览。后端优化 /api/file 的路径容错；前端接管 markdown <a> 标签点击，根据文件类型在右侧分屏动态加载 (iframe / mammoth / xlsx / react-markdown)。