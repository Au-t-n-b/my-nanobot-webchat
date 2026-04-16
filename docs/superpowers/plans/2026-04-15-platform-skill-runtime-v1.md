# Platform Skill Runtime V1 Implementation Plan（Async Resume）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-only protocol bridge + minimal runtime state that lets skills emit standardized runtime events and run in an **async-resume** model:

- Skill emits `hitl.*_request` then returns (no blocking)
- Platform persists a pending HITL item keyed by `requestId`
- User completes HITL
- Platform returns a unified `skill_runtime_result` to resume the skill

**Architecture:** Add a small generic bridge module in `nanobot/web` that accepts protocol envelopes (see `docs/handoffs/2026-04-15-平台事件协议草案-v1.md`) and maps them onto existing platform primitives (`MissionControlManager`, `SkillUiPatchPusher`, existing SSE task-status emission, and current artifact append behavior).

**Transport constraint (Hard Rule):** Reuse the existing `/api/chat` “fast-path intent” message body structure for both:

- **skill -> platform**: dispatch runtime events (envelopes) through chat fast-path intent
- **platform -> skill**: ingest `skill_runtime_result` through the same chat fast-path intent path

Do **not** introduce a new standalone endpoint like `/api/skill/runtime/result`. All runtime results must remain thread-scoped and session-scoped under chat.

The bridge must enforce core protocol rules: **requestId idempotency**, **dashboard single-writer**, and **logical URI** (no raw filesystem paths in public payloads).

**Tech Stack:** Python, `pytest`, aiohttp-side runtime hooks already used by `nanobot.web.routes`, existing SDUI patch helpers in `nanobot.web.skill_ui_patch`

**Persistence:** SQLite + `aiosqlite`

- Store pending HITL requests by `requestId`
- Store consumption status for idempotency
- Provide a minimal cleanup strategy for `expiresAt`

---

### Task 1: Define the protocol bridge contract

**Files:**
- Create: `nanobot/web/skill_runtime_bridge.py`
- Test: `tests/web/test_skill_runtime_bridge.py`
- Reference: `nanobot/web/mission_control.py`
- Reference: `nanobot/web/skill_ui_patch.py`
- Reference: `docs/handoffs/2026-04-15-平台事件协议草案-v1.md`

- [ ] **Step 1: Write the failing bridge tests**

```python
@pytest.mark.asyncio
async def test_emit_guidance_event_uses_mission_control() -> None:
    ...


@pytest.mark.asyncio
async def test_emit_dashboard_patch_uses_skill_ui_patch_builder() -> None:
    ...

@pytest.mark.asyncio
async def test_emit_dashboard_patch_enforces_single_writer_by_thread_and_doc() -> None:
    ...

@pytest.mark.asyncio
async def test_emit_hitl_requests_must_include_request_id() -> None:
    ...

@pytest.mark.asyncio
async def test_emit_hitl_request_is_idempotent_by_request_id() -> None:
    ...


@pytest.mark.asyncio
async def test_emit_unsupported_event_raises_value_error() -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_skill_runtime_bridge.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbol errors for `nanobot.web.skill_runtime_bridge`

- [ ] **Step 3: Write minimal protocol bridge implementation**

```python
SUPPORTED_SKILL_RUNTIME_EVENTS = {
    "chat.guidance",
    "dashboard.bootstrap",
    "dashboard.patch",
    "hitl.file_request",
    "hitl.choice_request",
    "hitl.confirm_request",
    "artifact.publish",
    "task_progress.sync",
}


async def emit_skill_runtime_event(*, envelope: dict[str, Any], thread_id: str, docman: Any = None) -> dict[str, Any]:
    ...
```

- [ ] **Step 4: Run bridge tests to verify they pass**

Run: `pytest tests/web/test_skill_runtime_bridge.py -v`
Expected: PASS with coverage for supported events and unsupported-event rejection

- [ ] **Step 5: Commit**

```bash
git add tests/web/test_skill_runtime_bridge.py nanobot/web/skill_runtime_bridge.py
git commit -m "feat: add skill runtime event bridge"
```

### Task 2: Wire dashboard bootstrap, artifact publish, and task-progress sync

**Files:**
- Modify: `nanobot/web/skill_runtime_bridge.py`
- Test: `tests/web/test_skill_runtime_bridge.py`
- Reference: `nanobot/web/module_skill_runtime.py`
- Reference: `nanobot/web/task_progress.py`

- [ ] **Step 1: Extend the failing tests for bootstrap, artifact, and progress events**

```python
@pytest.mark.asyncio
async def test_emit_dashboard_bootstrap_pushes_full_document() -> None:
    ...


@pytest.mark.asyncio
async def test_emit_artifact_publish_appends_all_items() -> None:
    ...

@pytest.mark.asyncio
async def test_emit_artifact_publish_rejects_raw_filesystem_paths() -> None:
    ...


@pytest.mark.asyncio
async def test_emit_task_progress_sync_normalizes_and_emits_status() -> None:
    ...
```

- [ ] **Step 2: Run targeted tests to verify they fail for the new behaviors**

Run: `pytest tests/web/test_skill_runtime_bridge.py -k "bootstrap or artifact or progress" -v`
Expected: FAIL because the new event branches are not implemented yet

- [ ] **Step 3: Implement the minimal event handlers**

```python
async def _emit_dashboard_bootstrap(...):
    ...


async def _emit_artifact_publish(...):
    ...


async def _emit_task_progress_sync(...):
    ...
```

- [ ] **Step 4: Re-run the targeted bridge tests**

Run: `pytest tests/web/test_skill_runtime_bridge.py -k "bootstrap or artifact or progress" -v`
Expected: PASS and confirm artifact append plus task-status emission payloads are captured

- [ ] **Step 5: Commit**

```bash
git add tests/web/test_skill_runtime_bridge.py nanobot/web/skill_runtime_bridge.py
git commit -m "feat: support dashboard and progress runtime events"
```

### Task 2.5: Add SQLite-backed pending HITL store + result ingest (async resume)

**Purpose:** Implement the async-resume backbone so that a skill can emit `hitl.*_request` and later be resumed by a unified `skill_runtime_result`, with strict idempotency by `requestId`.

**Files:**
- Create: `nanobot/web/pending_hitl_store.py`
- Modify: `nanobot/web/skill_runtime_bridge.py`
- Modify: `nanobot/web/routes.py` (reuse existing `/api/chat` fast-path intent routing)
- Test: `tests/web/test_pending_hitl_store.py`
- Test: `tests/web/test_skill_runtime_bridge.py`

#### Contract (Rules + Schema)

- **Rule: `requestId` is the primary key**
  - Every `hitl.*_request` must include `payload.requestId`.
  - Platform must persist exactly one pending record per `requestId` (unique constraint).
- **Rule: idempotent consume**
  - A given `requestId` may only transition from `pending -> consumed` once.
  - Duplicate result submissions for the same `requestId` must return the same consumption outcome (or be rejected deterministically), never resume twice.
- **Rule: async resume uses unified result**
  - Platform ingests `skill_runtime_result` containing: `threadId, skillName, requestId, action, status, result`.
  - Platform looks up the pending record by `requestId`, validates thread/skill match, marks it consumed, then dispatches/resumes the skill with the given `action` + `result`.
- **Rule: expiry**
  - If `expiresAt` is set on the pending record and current time exceeds it, platform must **auto timeout resume** using `status=timeout` to prevent zombie states.
  - Late-arriving user results for an already-timeouted `requestId` must return a deterministic response and must **not** trigger a second resume.

- **Rule: Zombie State Prevention**
  - The platform must ensure no pending HITL remains indefinitely without a terminal transition (`consumed|timeout|cancelled`).
  - A timeout transition is a first-class terminal outcome in async-resume.

- **Rule: Action Resolution on Timeout or Cancel (Fallback Routing Rule)**
  - When generating a `skill_runtime_result` with `status=timeout` or `status=cancel`, the platform MUST resolve the target `action` with strict priority:
    1. Use `on_cancel_action` if present on the stored pending record
    2. Else fallback to `resume_action`
  - The platform must not introduce any additional business routing logic beyond this priority rule.
  - Skill developers must ensure their `resume_action` handler checks `status != 'ok'` when `on_cancel_action` is omitted.

Suggested SQLite schema (minimal):

- `pending_hitl_requests`
  - `request_id TEXT PRIMARY KEY`
  - `thread_id TEXT NOT NULL`
  - `skill_name TEXT NOT NULL`
  - `skill_run_id TEXT NOT NULL` (run that emitted the request)
  - `event TEXT NOT NULL` (e.g. hitl.file_request)
  - `payload_json TEXT NOT NULL` (raw HITL spec for audit/debug)
  - `resume_action TEXT NOT NULL`
  - `on_cancel_action TEXT` (nullable)
  - `expires_at_ms INTEGER` (nullable)
  - `status TEXT NOT NULL` DEFAULT 'pending'  -- pending|consumed|expired|cancelled
  - `consumed_at_ms INTEGER` (nullable)
  - `created_at_ms INTEGER NOT NULL`

- `pending_hitl_results` (optional but recommended for idempotency replay)
  - `request_id TEXT PRIMARY KEY` (FK logical)
  - `status TEXT NOT NULL`
  - `result_json TEXT NOT NULL`
  - `created_at_ms INTEGER NOT NULL`

Implementation notes:

- Use `aiosqlite` and enforce idempotency via transaction + row-state check.
- Prefer `INSERT ... ON CONFLICT DO NOTHING` for pending creation, and a `SELECT FOR UPDATE` equivalent pattern via immediate transactions (`BEGIN IMMEDIATE`) for consume.

#### Steps

- [ ] **Step 1: Write failing store tests**

```python
@pytest.mark.asyncio
async def test_create_pending_hitl_is_idempotent_by_request_id(tmp_path) -> None:
    ...

@pytest.mark.asyncio
async def test_consume_result_is_idempotent_and_marks_consumed(tmp_path) -> None:
    ...

@pytest.mark.asyncio
async def test_consume_result_rejects_thread_or_skill_mismatch(tmp_path) -> None:
    ...

@pytest.mark.asyncio
async def test_timeout_resume_transitions_pending_to_timeout_and_is_idempotent(tmp_path) -> None:
    ...

@pytest.mark.asyncio
async def test_late_result_after_timeout_does_not_resume_twice(tmp_path) -> None:
    ...

@pytest.mark.asyncio
async def test_chat_fastpath_intent_skill_runtime_result_invokes_consume_result_idempotently(tmp_path) -> None:
    ...
```

- [ ] **Step 2: Run tests to verify fail**

Run: `pytest tests/web/test_pending_hitl_store.py -v`
Expected: FAIL because store module does not exist

- [ ] **Step 3: Implement `pending_hitl_store.py`**
  - `create_pending_request(envelope)`
  - `get_pending_request(request_id)`
  - `consume_result(result_envelope)` (transactional)
  - `timeout_expired_requests(now_ms)` (transactional; idempotent)

- [ ] **Step 4: Wire bridge to persist pending on `hitl.*_request`**
  - When receiving `hitl.file_request/choice_request/confirm_request`, validate `requestId`, persist pending record, then emit the UI card as before.

- [ ] **Step 5: Add `skill_runtime_result` ingest via chat fast-path intent**
  - Reuse the `/api/chat` fast-path intent message structure
  - **Hard Rule:** Use a dedicated intent name: `skill_runtime_result` (must not be renamed)
  - The intent payload must be the `skill_runtime_result` schema defined in `docs/handoffs/2026-04-15-平台事件协议草案-v1.md`
  - Calls `consume_result()` and returns a deterministic response for duplicates
  - Triggers the skill resume execution (integration stub acceptable in v1; ensure the contract is stable)

- [ ] **Step 5.1: Add auto-timeout processing**
  - Implement a minimal mechanism to drive `timeout_expired_requests(now_ms)`:
    - Option A: periodic background task in web process
    - Option B (acceptable v1): run timeout processing opportunistically on each ingest/dispatch
  - Ensure timeout resume emits/dispatches a `skill_runtime_result` with `status=timeout` and resolves the `action` using the Fallback Routing Rule (`on_cancel_action` if present, else `resume_action`).

- [ ] **Step 6: Re-run tests**

Run: `pytest tests/web/test_pending_hitl_store.py tests/web/test_skill_runtime_bridge.py -k "hitl or result" -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add nanobot/web/pending_hitl_store.py nanobot/web/skill_runtime_bridge.py nanobot/web/routes.py tests/web/test_pending_hitl_store.py tests/web/test_skill_runtime_bridge.py
git commit -m "feat: persist pending HITL and ingest runtime results"
```

### Task 3: Add a chat-card dispatch entrypoint for runtime events

**Files:**
- Modify: `nanobot/web/skill_runtime_bridge.py`
- Modify: `nanobot/web/routes.py`
- Test: `tests/web/test_skill_manifest_fastpath.py`
- Create or Modify: `tests/web/test_skill_runtime_bridge.py`

- [ ] **Step 1: Write failing dispatch tests for a new fast-path verb**

```python
@pytest.mark.asyncio
async def test_dispatch_skill_runtime_event_intent_executes_bridge() -> None:
    ...


@pytest.mark.asyncio
async def test_handle_chat_skill_runtime_event_returns_run_finished() -> None:
    ...
```

- [ ] **Step 2: Run the dispatch-focused tests to verify they fail**

Run: `pytest tests/web/test_skill_runtime_bridge.py tests/web/test_skill_manifest_fastpath.py -k "runtime_event" -v`
Expected: FAIL because the new verb is not routed yet

- [ ] **Step 3: Implement the new dispatch entrypoint and route hookup**

```python
async def dispatch_skill_runtime_intent(...):
    ...


if not handled:
    handled, hitl_message = await dispatch_skill_runtime_intent(...)
```

- [ ] **Step 4: Re-run the dispatch tests**

Run: `pytest tests/web/test_skill_runtime_bridge.py tests/web/test_skill_manifest_fastpath.py -k "runtime_event" -v`
Expected: PASS and verify `RunFinished.message` reflects the bridge summary

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/routes.py nanobot/web/skill_runtime_bridge.py tests/web/test_skill_runtime_bridge.py tests/web/test_skill_manifest_fastpath.py
git commit -m "feat: route skill runtime events through chat fast-path"
```

### Task 4: Verify existing flows stay green

**Files:**
- No code changes expected
- Test: `tests/web/test_skill_runtime_bridge.py`
- Test: `tests/web/test_skill_manifest_fastpath.py`
- Test: `tests/test_module_skill_runtime.py`

- [ ] **Step 1: Run bridge and manifest regression tests**

Run: `pytest tests/web/test_skill_runtime_bridge.py tests/web/test_skill_manifest_fastpath.py -v`
Expected: PASS

- [ ] **Step 2: Run the focused module runtime regression tests**

Run: `pytest tests/test_module_skill_runtime.py -k "boilerplate or smart_survey or modeling_simulation or task_progress" -v`
Expected: PASS and show no regressions in current module-flow behavior

- [ ] **Step 3: Review the diff for accidental scope creep**

Run: `git diff --stat`
Expected: only `nanobot/web/routes.py`, `nanobot/web/skill_runtime_bridge.py`, and related tests/plan docs changed

- [ ] **Step 4: Commit verification-only updates if needed**

```bash
git add docs/superpowers/plans/2026-04-15-platform-skill-runtime-v1.md
git commit -m "docs: add platform skill runtime v1 plan"
```

## Self-Review

- Spec coverage: this plan covers the phase-1 event set agreed in the 2026-04-15 handoff docs, including `hitl.choice_request` and `hitl.confirm_request`, and focuses on platform-side bridge + idempotent pending-HITL persistence; it intentionally excludes full module migrations.
- Placeholder scan: the plan names exact files, tests, commands, and expected outcomes; no `TBD` or deferred pseudo-steps remain.
- Type consistency: the bridge uses one event-envelope entrypoint and one chat fast-path dispatch surface so follow-up module migrations can target a stable API; the bridge enforces `requestId` idempotency, dashboard single-writer, and logical URI rules.
