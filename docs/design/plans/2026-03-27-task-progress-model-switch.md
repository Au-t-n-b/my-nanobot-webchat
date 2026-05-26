# Task Progress + Model Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增任务进度读取接口与模型动态切换能力，并完成前端模型选择器与任务看板联调。

**Architecture:** 后端在 `routes.py` 增加 `GET /api/task-status`，并扩展 `POST /api/chat` 接收并透传 `model_name`（请求级生效）。前端通过 `ModelSelector` 维护当前选择模型并在发送消息时附带参数，同时新增 `TaskProgressBar` 组件以低耦合轮询 `/api/task-status` 并展示模块状态。

**Tech Stack:** Python (aiohttp, pytest), TypeScript (React 19, Next.js 15), SSE, existing AGUI runtime.

---

## File Structure / Responsibilities

- `nanobot/nanobot/web/routes.py`
  - 新增 `handle_task_status`
  - 扩展 `handle_chat` 解析/校验 `model_name`
  - 注册 `/api/task-status` 与对应 `OPTIONS`
- `nanobot/nanobot/agent/loop.py`
  - 为请求级模型覆盖补充可选参数透传链路（`process_direct` 到 provider 调用）
- `nanobot/tests/web/test_api_chat.py`
  - 补充 `model_name` 输入校验与传递行为的回归测试
- `nanobot/tests/web/test_task_status.py` (new)
  - 覆盖 `/api/task-status` 三类场景：无文件、合法 JSON、非法 JSON
- `nanobot/frontend/hooks/useAgentChat.ts`
  - 扩展 `sendMessage(text, modelName?)`
  - 发送 `model_name`
  - 处理 `RunStarted` 模型回显状态
- `nanobot/frontend/components/ModelSelector.tsx` (new)
  - 模型下拉选择器 UI
- `nanobot/frontend/components/TaskProgressBar.tsx` (new)
  - 轮询任务进度与节点/悬浮细分步骤渲染
- `nanobot/frontend/components/ChatArea.tsx`
  - 在消息列表上方挂载 `TaskProgressBar`
- `nanobot/frontend/app/page.tsx`
  - 持有 `selectedModel`
  - 将模型传入 `sendMessage`
  - 在顶部栏挂载 `ModelSelector`

---

### Task 1: Backend task-status API contract

**Files:**
- Modify: `nanobot/nanobot/web/routes.py`
- Test: `nanobot/tests/web/test_task_status.py` (create)

- [ ] **Step 1: Write failing tests for `/api/task-status`**

```python
@pytest.mark.asyncio
async def test_task_status_returns_default_when_file_missing():
    ...
    assert resp.status == 200
    assert body["modules"][0]["status"] == "pending"

@pytest.mark.asyncio
async def test_task_status_returns_file_json_when_valid():
    ...

@pytest.mark.asyncio
async def test_task_status_returns_500_when_invalid_json():
    ...
    assert resp.status == 500
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/web/test_task_status.py -v`  
Expected: FAIL (route not found / assertions fail)

- [ ] **Step 3: Implement `handle_task_status`**

```python
async def handle_task_status(request: web.Request) -> web.Response:
    workspace = _agui_workspace_root(request.app[CONFIG_KEY])
    target = workspace / "task_progress.json"
    if not target.exists():
        return web.json_response(DEFAULT_TASK_STATUS)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return web.json_response(payload)
    except json.JSONDecodeError:
        return web.json_response({"detail": "invalid task_progress.json"}, status=500)
```

- [ ] **Step 4: Register route and OPTIONS**

Run change in `setup_routes(app)`:
- `app.router.add_get("/api/task-status", handle_task_status)`
- `app.router.add_options("/api/task-status", handle_options)`

- [ ] **Step 5: Re-run tests**

Run: `pytest tests/web/test_task_status.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nanobot/web/routes.py tests/web/test_task_status.py
git commit -m "feat(web): add task status api with default contract"
```

---

### Task 2: Request-scoped model_name backend flow

**Files:**
- Modify: `nanobot/nanobot/web/routes.py`
- Modify: `nanobot/nanobot/agent/loop.py`
- Test: `nanobot/tests/web/test_api_chat.py`

- [ ] **Step 1: Add failing tests for model_name parsing/validation**

```python
@pytest.mark.asyncio
async def test_post_chat_rejects_non_string_model_name():
    ...
    assert resp.status == 400

@pytest.mark.asyncio
async def test_post_chat_accepts_optional_model_name():
    ...
    assert resp.status == 200
```

- [ ] **Step 2: Run specific failing tests**

Run: `pytest tests/web/test_api_chat.py -k "model_name" -v`  
Expected: FAIL

- [ ] **Step 3: Parse and validate `model_name` in `handle_chat`**

```python
raw_model = data.get("model_name")
model_name = None
if raw_model is not None:
    if not isinstance(raw_model, str):
        return web.json_response({"detail": "model_name must be a string"}, status=400)
    model_name = raw_model.strip() or None
```

- [ ] **Step 4: Thread model_name through loop call chain**

Implementation target:
- `process_direct(..., model_name: str | None = None)`
- propagate through internal methods to provider call
- select effective model as `model_name or default_model`

- [ ] **Step 5: Define effective-model return path for SSE**

Make effective model observable from route layer:
- option A: extend process result with `effective_model`
- option B: callback/event includes effective model
- route must read this value for `RunStarted.model`

- [ ] **Step 6: Ensure `RunStarted.model` reflects effective model**

In `routes.py`, emit model field from the same effective model used at provider call site.

- [ ] **Step 7: Add regression assertion for RunStarted model**

Add test in `tests/web/test_api_chat.py`:
- request with `model_name`
- assert SSE contains `event: RunStarted` payload where `model` equals expected effective model

- [ ] **Step 8: Run chat API regression tests**

Run: `pytest tests/web/test_api_chat.py -v`  
Expected: PASS (including existing 409/SSE lifecycle tests)

- [ ] **Step 9: Commit**

```bash
git add nanobot/web/routes.py nanobot/agent/loop.py tests/web/test_api_chat.py
git commit -m "feat(chat): support request-scoped model_name override"
```

---

### Task 3: Frontend model selector wiring

**Files:**
- Create: `nanobot/frontend/components/ModelSelector.tsx`
- Modify: `nanobot/frontend/app/page.tsx`
- Modify: `nanobot/frontend/hooks/useAgentChat.ts`

- [ ] **Step 1: Add/adjust types for selected model**

Define reusable union type:

```ts
type AvailableModel = "glm-4" | "glm-4v" | "glm-4.7";
```

- [ ] **Step 2: Create `ModelSelector` component**

```tsx
export function ModelSelector({ value, onChange }: Props) {
  return <select ...>{...}</select>;
}
```

- [ ] **Step 3: Lift `selectedModel` state in `page.tsx`**

- initialize default to `"glm-4"`
- render selector in top control bar
- pass `selectedModel` into send path

- [ ] **Step 4: Extend `sendMessage` signature**

In `useAgentChat.ts`:
- `sendMessage(text: string, modelName?: string)`
- include `model_name` in request body

- [ ] **Step 5: Handle `RunStarted` model echo**

In SSE handler:
- parse `RunStarted`
- store `effectiveModel` state (for display consistency)

- [ ] **Step 6: Run lint**

Run: `npm run lint` (working dir: `frontend`)  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/components/ModelSelector.tsx frontend/app/page.tsx frontend/hooks/useAgentChat.ts
git commit -m "feat(frontend): add model selector and chat model payload"
```

---

### Task 4: Frontend task progress board

**Files:**
- Create: `nanobot/frontend/components/TaskProgressBar.tsx`
- Modify: `nanobot/frontend/components/ChatArea.tsx`

- [ ] **Step 1: Define API contract types**

```ts
type ModuleStatus = "pending" | "running" | "completed";
type TaskStatusPayload = { overall: ..., modules: ... };
```

- [ ] **Step 2: Implement polling logic with lifecycle controls**

- poll every 2000ms
- immediate fetch on mount/resume
- pause when `document.hidden`
- stop when `doneCount === totalCount`
- allow explicit stop on run terminal signal prop

- [ ] **Step 3: Define run-terminal signal prop chain**

Wire signal explicitly:
- `useAgentChat` exposes run terminal status marker
- `page.tsx` passes marker to `ChatArea`
- `ChatArea` passes marker to `TaskProgressBar`
- `TaskProgressBar` clears interval when marker indicates terminal run state

- [ ] **Step 4: Implement UI nodes + tooltip**

- 6 horizontal nodes
- visual mapping:
  - `pending`: muted
  - `running`: highlighted + spinner
  - `completed`: checkmark + strong color
- hover popover shows `steps` status list

- [ ] **Step 5: Mount in `ChatArea` above `MessageList`**

- keep state local to component
- avoid changing message list data flow

- [ ] **Step 6: Add minimal component behavior test (if test infra exists)**

Test target:
- first fetch success populates progress
- second fetch fails keeps previous data
- terminal signal / doneCount condition stops polling

If no frontend test runner exists, add a TODO note in PR and keep manual verification list strict.

- [ ] **Step 7: Run lint**

Run: `npm run lint` (working dir: `frontend`)  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/components/TaskProgressBar.tsx frontend/components/ChatArea.tsx
git commit -m "feat(frontend): add task progress board with smart polling"
```

---

### Task 5: End-to-end regression verification

**Files:**
- Verify only (no new files required)

- [ ] **Step 1: Backend API checks**

Run:
- `pytest tests/web/test_task_status.py -v`
- `pytest tests/web/test_api_chat.py -v`

Expected: all PASS

- [ ] **Step 2: Task-status contract assertions**

In `tests/web/test_task_status.py`, ensure assertions cover:
- `overall.totalCount === len(modules)`
- `overall.doneCount === count(status == "completed")`
- all module status in `{"pending", "running", "completed"}`
- each `steps` item follows `{id,name,done}`

- [ ] **Step 3: Frontend static checks**

Run: `npm run lint` (working dir: `frontend`)  
Expected: PASS

- [ ] **Step 4: Manual smoke checks**

- 切换模型后发送消息，确认请求体带 `model_name`
- 观察 SSE `RunStarted.model` 与 UI 模型标签一致
- 删除 `task_progress.json`，看板展示默认模板
- 写入合法 `task_progress.json`，看板 2 秒内刷新
- 写入非法 JSON，前端保持上次数据并记录错误

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: deliver task progress api and model switch ui flow"
```

