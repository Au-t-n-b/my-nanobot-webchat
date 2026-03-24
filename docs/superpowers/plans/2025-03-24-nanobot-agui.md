# Nanobot AGUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Next.js + aiohttp split-stack AGUI: SSE chat API wired to Nanobot `process_direct`, HITL, choices modal, and file preview—per [spec](../specs/2025-03-24-nanobot-agui-design.md) and [CURSOR_REFACTOR_PLAN.md](../../CURSOR_REFACTOR_PLAN.md).

**Architecture:** New package `nanobot/web/` hosts an aiohttp app with `/api/chat` (SSE), `/api/approve-tool`, `GET /api/file`. A Typer command (e.g. `nanobot agui`) boots the HTTP server and constructs `AgentLoop` using the same `_load_runtime_config` / `_make_provider` patterns as [`nanobot/cli/commands.py`](../../../nanobot/cli/commands.py) (`agent` / `gateway` commands). Existing `gateway` remains the channel+cron+heartbeat process; AGUI is a **separate** entry point to avoid conflating responsibilities. Frontend lives in `frontend/` with `useAgentChat` parsing SSE without Vercel AI SDK.

**Tech Stack:** Python 3.11+, aiohttp, pytest, pytest-aiohttp (or aiohttp test client); Next.js App Router, TypeScript, Tailwind, Lucide; local npm only (no CDN).

**References:** @superpowers:subagent-driven-development @superpowers:executing-plans @superpowers:verification-before-completion

---

## File map (create / modify)

| Path | Responsibility |
|------|----------------|
| [`pyproject.toml`](../../../pyproject.toml) | Add `aiohttp` dependency; optional `pytest-aiohttp` in dev |
| `nanobot/web/__init__.py` | Package marker |
| `nanobot/web/sse.py` | `format_sse(event: str, data: dict) -> bytes` (single-line JSON, `\n\n` delimiter) |
| `nanobot/web/run_registry.py` | Per-`threadId` active run tracking for HTTP 409; register/unregister on stream lifecycle |
| `nanobot/web/paths.py` | `normalize_file_query(path: str) -> str`; resolve relative paths against `Config.workspace_path` |
| `nanobot/web/routes.py` | aiohttp route handlers: chat, approve-tool, file, CORS preflight |
| `nanobot/web/app.py` | `create_app(config: Config, agent: AgentLoop | None, ...)` — dependency injection for tests |
| `nanobot/web/keys.py` | aiohttp `AppKey` 定义（消除 string key 警告） |
| `nanobot/cli/commands.py` | New command `agui` (name TBD): load config, build AgentLoop (Step 1: `agent=None` or stub), `web.run_app` |
| `tests/web/test_sse.py` | Unit tests for SSE framing |
| `tests/web/test_api_chat.py` | Integration: POST `/api/chat` returns SSE sequence; 409 on double same thread |
| `tests/web/test_api_file.py` | `GET /api/file` path normalization + absolute/relative (Step 6 or stub in Step 1) |
| `frontend/` | Step 2+: create-next-app output |

---

### Task 1: Step 1 — Backend API shell, fake SSE, CORS, 409

**Files:**
- Create: `nanobot/web/__init__.py`, `nanobot/web/sse.py`, `nanobot/web/run_registry.py`, `nanobot/web/keys.py`, `nanobot/web/routes.py`, `nanobot/web/app.py`
- Modify: [`pyproject.toml`](../../../pyproject.toml), [`nanobot/cli/commands.py`](../../../nanobot/cli/commands.py)
- Test: `tests/web/test_sse.py`, `tests/web/test_api_chat.py`

**Contract (frozen):** Success stream ends with `RunFinished` **without** `error` key. Error streams: `Error` then `RunFinished` **with** `error: {code, message}`.

- [x] **Step 1.1: Write failing test for SSE framing**

```python
# tests/web/test_sse.py
from nanobot.web.sse import format_sse

def test_format_sse_single_event():
    out = format_sse("RunStarted", {"threadId": "t", "runId": "r", "model": "m"})
    assert b"event: RunStarted\n" in out
    assert b'data: {"threadId":' in out or b'"threadId"' in out
    assert out.endswith(b"\n\n")
```

Run: `pytest tests/web/test_sse.py::test_format_sse_single_event -v`  
Expected: **FAIL** (import/module missing).

- [x] **Step 1.2: Implement `format_sse`** in `nanobot/web/sse.py` using `json.dumps(..., ensure_ascii=False, separators=(",", ":"))` and UTF-8.

Run: `pytest tests/web/test_sse.py -v` → **PASS**.

- [x] **Step 1.3: Write failing integration test** `tests/web/test_api_chat.py`: create app with **no** real agent; POST `/api/chat` with JSON `{"threadId":"t1","runId":"r1","messages":[],"humanInTheLoop":false}`; read body; assert sequence contains `RunStarted`, `TextMessageContent`, `RunFinished`.

Run: `pytest tests/web/test_api_chat.py -v` → **FAIL**.

- [x] **Step 1.4: Implement minimal aiohttp app** in `app.py` + `routes.py`:
  - `POST /api/chat`: response **`Content-Type: text/event-stream`** (spec §4.1); validate `threadId`, `runId` present; **run_registry** register `threadId` → fail with **409** if already active; yield fake `RunStarted`, 2× `TextMessageContent`, `RunFinished`; unregister in `finally`.
  - `OPTIONS` + `Access-Control-Allow-Origin: http://localhost:3000` (and configurable list via env `NANOBOT_AGUI_CORS_ORIGINS` comma-separated, default dev origin), `Allow-Methods`, `Allow-Headers: Content-Type`.
  - `POST /api/approve-tool`: **501** JSON stub body `{"detail":"not implemented"}`.
  - `GET /api/file`: **501** stub for Step 1.

Run: `pytest tests/web/test_api_chat.py -v` → **PASS**.

- [x] **Step 1.5: Add test for 409**: two concurrent POSTs same `threadId` — second returns 409 before SSE body (or assert 409 with JSON — pick one and document in handler).

Run: `pytest tests/web/test_api_chat.py -v` → **PASS**.

- [x] **Step 1.6: Typer command** e.g. `nanobot agui --port 8765` calling `aiohttp.web.run_app` on `create_app(...)`. Step 1: pass `agent_loop=None`; fake stream only.

Run manual: `nanobot agui -p 8765` then `curl -N -X POST http://127.0.0.1:8765/api/chat -H "Content-Type: application/json" -d "{\"threadId\":\"a\",\"runId\":\"b\",\"messages\":[],\"humanInTheLoop\":false}"` — expect SSE lines.

- [x] **Step 1.7: Commit** — `feat(web): aiohttp AGUI stub with fake SSE, CORS, 409`

---

### Task 2: Step 1b — Wire `process_direct` (optional same PR as 1 or immediate follow-up)

**Files:**
- Modify: `nanobot/web/routes.py`, `nanobot/web/app.py`, `nanobot/cli/commands.py`
- Test: extend `tests/web/test_api_chat.py` with mocked `AgentLoop` or contract test with env `NANOBOT_AGUI_FAKE=1`

- [x] **Step 2.1:** In `agui` command, construct `AgentLoop` like [`commands.py` `agent` command](../../../nanobot/cli/commands.py) (lines ~709–738): `MessageBus`, `_make_provider`, `CronService`; omit explicit `SessionManager` if mirroring `agent` (loop defaults to `SessionManager(workspace)` per `AgentLoop.__init__`). 增加 `--fake` 仅假流。

- [x] **Step 2.2:** In `POST /api/chat`, extract user text: **last message with `role=="user"`** string `content`; if missing, **400**. Pass to `process_direct(content, session_key=threadId, channel="web", chat_id=threadId, on_progress=..., on_stream=..., on_stream_end=...)`。

- [x] **Step 2.3:** Map callbacks → SSE per [spec §5](../specs/2025-03-24-nanobot-agui-design.md). **`on_progress` 签名:** `tool_hint=False` → `StepStarted` thinking；`tool_hint=True` → `StepStarted` tool。`RunStarted.model`: `agent_loop.model`. 异常：`Error` + `RunFinished` 带 `error`；`app.on_cleanup` 调用 `close_mcp`。

- [x] **Step 2.4:** Run pytest + commit（真实 LLM 需本地有 key 后手动 curl 带 `messages`）。

---

### Task 3: Step 2 — Next.js + `useAgentChat`

**Files:**
- Create: `frontend/` via `npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir=false` (adjust flags to match repo convention; **no** src dir if plan prefers `app/` at root of frontend).
- Create: `frontend/hooks/useAgentChat.ts`, `frontend/.env.local.example`

- [ ] **Step 3.1:** `create-next-app` (offline mirror / private registry per org policy).

- [ ] **Step 3.2:** Implement `useAgentChat`: `fetch(API_BASE + '/api/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body })`; parse SSE with `response.body.getReader()` + TextDecoder, split on `\n\n`, handle `event:` / `data:` lines; accumulate `TextMessageContent.delta`; set state for `pendingTool` / `pendingChoices` when events arrive (stub handlers OK).

- [ ] **Step 3.3:** `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8765` in `.env.local.example`.

- [ ] **Step 3.4:** 持久化 `threadId`（如 `localStorage`）以符合 spec D2 与多刷新场景；最小页面证明 SSE 文本展示。 Commit。

---

### Task 4: Step 3 — Three-column UI (dark zinc)

**Files:**
- Create/modify: `frontend/app/page.tsx`, `frontend/components/Sidebar.tsx`, `ChatArea.tsx`, `MessageList.tsx`, `ChatInput.tsx`, `PreviewPanel.tsx` (shell)

- [ ] **Step 4.1:** Layout: Sidebar | Chat | Preview (collapsible). Tailwind `bg-zinc-950 text-zinc-100`. Lucide icons.

- [ ] **Step 4.2:** Message bubbles: user vs assistant; fold `StepStarted` in UI. Commit.

---

### Task 5: Step 4 — HITL (`ToolPending` + `/api/approve-tool`)

**Files:**
- Modify: `nanobot/web/routes.py`, `nanobot/agent/...` (tool execution hook)
- Modify: `frontend/components/...` confirmation card

**HITL 实现选定（避免分叉）：** 以 **Web 层 `(threadId, runId, toolCallId) -> asyncio.Future` 注册表** 为唯一挂起点；工具侧在执行前查询当前请求上下文并 `await future`（由 `approve-tool` 注入结果）。**不**并行采用第二套「仅改 ToolRegistry」而未接 Future 的路径。

**`humanInTheLoop`：** 请求体字段在 Step 1 已解析；Step 5 需写明首版是否读取该布尔（例如仅当 `true` 时对标记为敏感的工具挂起），若忽略则文档注明「当前未使用，默认行为为…」以免与产品预期偏差。

- [ ] **Step 5.1:** Backend: on sensitive tool, pause and emit `ToolPending`; store Future in registry; `/api/approve-tool` resolves Future; **404** if no pending (spec).

- [ ] **Step 5.2:** Frontend: render card; POST approve; resume stream consumption. Tests + commit.

---

### Task 6: Step 5 — `RunFinished.choices` modal

**Files:**
- Modify: agent/tooling — 仓库内可能尚无 `present_choices`：**新增**工具或等价机制，在需选择题时把 `choices` 写入当次 `RunFinished`（与蓝图一致）
- Create: `frontend/components/ChoicesModal.tsx`

- [ ] **Step 6.1:** 后端：注册 `present_choices`（或命名一致的工具），在 loop 结束路径将 `choices` 附加到 `RunFinished`。
- [ ] **Step 6.2:** 前端：解析 `RunFinished.choices`；Tailwind 居中 Modal；点选后作为下一条 user 消息再走 `useAgentChat`。 Commit。

---

### Task 7: Step 6 — `/api/file` + preview panel

**Files:**
- Create: `nanobot/web/paths.py`
- Modify: `nanobot/web/routes.py` — implement `GET /api/file` using `normalize_file_query`; absolute as-is; relative → `Path(config.workspace_path) / path` with `resolve()`; **no** sandbox beyond spec D6 (PoC)
- Modify: `frontend/components/PreviewPanel.tsx` + link interception: iframe/img, `srcDoc` HTML, react-markdown, xlsx, mammoth, mermaid (**all npm deps**, no CDN)

- [ ] **Step 7.1:** Backend file handler + content-type mapping + tests.

- [ ] **Step 7.2:** Frontend preview by extension. Commit.

---

## Verification commands (recurring)

```bash
cd d:\code\nanobot
pytest tests/web/ -v
cd frontend && npm run build && npm run lint
```

---

## Handoff notes

- **Do not** remove or replace `gateway` command in Step 1; AGUI HTTP is additive.
- **`/api/approve-tool` not-found:** use **HTTP 404** (per spec recommendation).
- **Success `RunFinished`:** **omit** `error` key entirely (do not send `"error": null`).

---

## Plan revision

- **2025-03-24:** Initial plan from approved spec + CURSOR_REFACTOR_PLAN.
- **2025-03-24:** Plan review **Approved**; merged advisory (SSE `Content-Type`, `on_progress`/`tool_hint`, HITL Future-only, `present_choices` sub-steps, `threadId` persistence, `humanInTheLoop` note).
