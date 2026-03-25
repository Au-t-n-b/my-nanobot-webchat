# Nanobot AGUI Phase 3 Sidebar Ecosystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** �?AGUI 实现 Phase 3（技能树 API 联动、动态文件索引与 Tooltip、安全回收站），并与现有预览面板稳定联动�?

**Architecture:** 后端�?`nanobot/web/` 增加文件系统 API（skills/open-folder/trash-files），skills 根目录固定为 `~/.nanobot/workspace/skills`（测试可注入替身目录但不改变生产语义），统一�?realpath 越界校验；前端以 Sidebar 状态机消费这些 API，并把技能与文件点击统一映射到既�?`PreviewPanel` 预览路径。删除链路采用“越界整批拒绝、合法路径允许部分成功”的策略，保证安全优先�?

**Tech Stack:** aiohttp, pathlib, send2trash, pytest + aiohttp test client, Next.js App Router, TypeScript, React state hooks

**Spec:** `docs/superpowers/specs/2026-03-24-nanobot-agui-phase3-sidebar-ecosystem-design.md`

---

## File map (create / modify)

| Path | Responsibility |
|---|---|
| `nanobot/web/skills.py` (new) | skills root 解析、扫描、排序、返回结�?|
| `nanobot/web/fs_ops.py` (new) | open-folder / trash-files 的路径校验与平台调用封装 |
| `nanobot/web/routes.py` (modify) | 新增 `/api/skills`、`/api/open-folder`、`/api/trash-files` |
| `tests/web/test_api_skills.py` (new) | skills API 契约测试 |
| `tests/web/test_api_open_folder.py` (new) | open-folder 行为与安全测�?|
| `tests/web/test_api_trash.py` (new) | trash-files 批量与安全测�?|
| `frontend/components/Sidebar.tsx` (modify) | skills 列表、刷新、打开目录、回收站交互、Tooltip |
| `frontend/app/page.tsx` (modify) | 传�?Phase 3 所需 props 与联�?|
| `frontend/hooks/useAgentChat.ts` (modify) | 暴露 messages 给侧栏索引（若当前层级不便，保持最小改动） |
| `frontend/lib/fileIndex.ts` (new) | 从消息抽�?`/api/file?path=...`、去重与文件名提�?|

---

### Task 1: Backend skill discovery API (`GET /api/skills`)

**Files:**
- Create: `nanobot/web/skills.py`
- Modify: `nanobot/web/routes.py`
- Test: `tests/web/test_api_skills.py`

- [x] **Step 1: Write failing test for auto-create when skills dir missing**

```python
@pytest.mark.asyncio
async def test_get_skills_auto_create_and_empty(tmp_path):
    # setup app with workspace tmp_path
    # call GET /api/skills
    # assert 200 and {"items": []}
    # assert (tmp_path / "skills").exists()
```

- [x] **Step 2: Run failing test**

Run: `pytest tests/web/test_api_skills.py::test_get_skills_auto_create_and_empty -v`  
Expected: FAIL (route/handler missing)

- [x] **Step 3: Write failing test for scan + A->Z ordering**

```python
@pytest.mark.asyncio
async def test_get_skills_scans_skill_md_and_sorts(tmp_path):
    # create skills/beta/SKILL.md and skills/Alpha/SKILL.md
    # assert names order uses name.lower() stable sort => Alpha, beta
```

- [x] **Step 3.1: Write failing tests for unified error payload contract**

```python
@pytest.mark.asyncio
async def test_skills_error_payload_shape_on_internal_error(...):
    # assert response json has {"error":{"code","message",...}}
```

- [x] **Step 4: Run failing ordering test**

Run: `pytest tests/web/test_api_skills.py::test_get_skills_scans_skill_md_and_sorts -v`  
Expected: FAIL

- [x] **Step 5: Implement `nanobot/web/skills.py` minimal scan logic**

```python
def get_skills_root() -> Path: ...
def list_skills() -> list[dict]: ...
# ensures root exists, scans */SKILL.md, returns absolute paths
```

- [x] **Step 6: Add `GET /api/skills` in routes**

Run: `pytest tests/web/test_api_skills.py -v`  
Expected: PASS

- [x] **Step 7: Commit Task 1**

```bash
git add nanobot/web/skills.py nanobot/web/routes.py tests/web/test_api_skills.py
git commit -m "feat(web): add /api/skills with workspace skills discovery"
```

---

### Task 2: Backend open-folder API (`POST /api/open-folder`)

**Files:**
- Create: `nanobot/web/fs_ops.py`
- Modify: `nanobot/web/routes.py`
- Test: `tests/web/test_api_open_folder.py`

- [x] **Step 1: Write failing test for open directory**

```python
@pytest.mark.asyncio
async def test_open_folder_directory_ok(...):
    # POST target=<workspace>/skills/foo
    # assert 200 {"ok": True}
```

- [x] **Step 2: Write failing test for file target platform behavior**

```python
def test_open_file_windows_selects_file(...): ...
def test_open_file_non_windows_opens_parent(...): ...
```

- [x] **Step 3: Write failing tests for security**

```python
@pytest.mark.asyncio
async def test_open_folder_rejects_escape(...): ...

@pytest.mark.asyncio
async def test_open_folder_rejects_symlink_escape(...): ...
```

- [x] **Step 3.1: Write failing test for not-found + error payload**

```python
@pytest.mark.asyncio
async def test_open_folder_not_found_returns_404_with_error_payload(...): ...
```

- [x] **Step 4: Run tests to verify failures**

Run: `pytest tests/web/test_api_open_folder.py -v`  
Expected: FAIL

- [x] **Step 5: Implement realpath guard + platform open in `fs_ops.py`**

```python
def resolve_in_workspace(target: str, workspace: Path) -> Path: ...
def open_in_os(path: Path) -> None: ...
```

- [x] **Step 6: Add `/api/open-folder` route + unified error mapping**

Run: `pytest tests/web/test_api_open_folder.py -v`  
Expected: PASS

- [x] **Step 7: Commit Task 2**

```bash
git add nanobot/web/fs_ops.py nanobot/web/routes.py tests/web/test_api_open_folder.py
git commit -m "feat(web): add /api/open-folder with workspace-bound safety"
```

---

### Task 3: Backend trash API (`POST /api/trash-files`)

**Files:**
- Modify: `nanobot/web/fs_ops.py`, `nanobot/web/routes.py`
- Test: `tests/web/test_api_trash.py`

- [x] **Step 1: Write failing tests for input validation**

```python
@pytest.mark.asyncio
async def test_trash_files_rejects_empty_paths(...): ...

@pytest.mark.asyncio
async def test_trash_files_rejects_any_escape_all_or_nothing(...): ...
```

- [x] **Step 1.1: Write failing tests for dedupe + directory target**

```python
@pytest.mark.asyncio
async def test_trash_files_dedupes_paths(...): ...

@pytest.mark.asyncio
async def test_trash_files_accepts_directory_target(...): ...
```

- [x] **Step 2: Write failing tests for partial success semantics**

```python
@pytest.mark.asyncio
async def test_trash_files_partial_success_returns_deleted_and_failed(...): ...
```

- [x] **Step 3: Write failing test for symlink escape rejection**

```python
@pytest.mark.asyncio
async def test_trash_files_rejects_symlink_escape(...): ...
```

- [x] **Step 3.1: Write failing tests for error payload contract (400/500)**

```python
@pytest.mark.asyncio
async def test_trash_files_error_payload_shape(...): ...
```

- [x] **Step 4: Run tests to verify failures**

Run: `pytest tests/web/test_api_trash.py -v`  
Expected: FAIL

- [x] **Step 5: Implement route + send2trash integration**

```python
# dedupe paths
# preflight: if any escape => 400 and do nothing
# valid set: delete one by one, collect deleted/failed
# ok = len(failed) == 0
```

- [x] **Step 6: Run test suite for Task 1-3**

Run: `pytest tests/web/test_api_skills.py tests/web/test_api_open_folder.py tests/web/test_api_trash.py -v`  
Expected: PASS

- [x] **Step 7: Commit Task 3**

```bash
git add nanobot/web/fs_ops.py nanobot/web/routes.py tests/web/test_api_trash.py
git commit -m "feat(web): add workspace-safe /api/trash-files with partial-success reporting"
```

---

### Task 4: Frontend sidebar skills list + preview linkage

**Files:**
- Modify: `frontend/components/Sidebar.tsx`, `frontend/app/page.tsx`
- Create: `frontend/lib/fileIndex.ts`
- Test: `frontend` component/manual validation

- [x] **Step 1: Add minimal automated tests (required)**

```ts
// Sidebar loads /api/skills
// renders loading/empty/error states
// clicking skill calls onPreviewPath(skillFile) and only SKILL.md
```

- [x] **Step 2: Run tests to verify failures**

Run: `cd frontend && npm test -- Sidebar`  
Expected: FAIL

- [x] **Step 3: Implement skills fetching + loading/empty/error states**

```tsx
useEffect(() => fetch("/api/skills"))
```

- [x] **Step 4: Implement refresh and open-folder actions**

```tsx
POST /api/open-folder with selected skill dir or skillFile
```

- [x] **Step 5: Wire skill click -> PreviewPanel with `SKILL.md` only**

Run: `cd frontend && npm run lint`  
Expected: PASS

- [x] **Step 6: Run automated tests + lint**

Run:
```bash
cd frontend
npm test -- Sidebar
npm run lint
```
Expected: PASS

- [x] **Step 7: Manual verify**

Run:
```bash
nanobot agui
cd frontend && npm run dev
```
Expected:
- Sidebar renders skills
- Clicking one opens `SKILL.md` preview
- Open-folder button works

- [x] **Step 8: Commit Task 4**

```bash
git add frontend/components/Sidebar.tsx frontend/app/page.tsx
git commit -m "feat(frontend): phase3 skills sidebar with preview and open-folder actions"
```

---

### Task 5: Dynamic file index + tooltip + trash confirmation flow

**Files:**
- Create: `frontend/lib/fileIndex.ts`
- Modify: `frontend/components/Sidebar.tsx`, `frontend/app/page.tsx`

- [x] **Step 1: Write failing extraction + interaction tests (required)**

```ts
// extract /api/file?path=... from assistant messages
// dedupe and render filename, keep full path as tooltip
// delete single/clear all requires confirm
// partial failure keeps failed items visible
```

- [x] **Step 2: Implement `extractIndexedFiles(messages)`**

```ts
export type IndexedFile = { path: string; fileName: string };
```

- [x] **Step 3: Render indexed file list with filename-only + title tooltip**

- [x] **Step 4: Implement delete single + clear all confirmation modal**

- [x] **Step 5: Hook modal confirm -> POST /api/trash-files**

- [x] **Step 6: Handle partial failure UI**

Expected:
- success items removed
- failed items retained

- [x] **Step 7: Run checks**

Run: `cd frontend && npm run lint && npm run build`  
Expected: PASS

- [x] **Step 7.1: Run required frontend automated tests**

Run:
```bash
cd frontend
npm test -- Sidebar fileIndex
```
Expected: PASS

- [x] **Step 8: Commit Task 5**

```bash
git add frontend/lib/fileIndex.ts frontend/components/Sidebar.tsx frontend/app/page.tsx
git commit -m "feat(frontend): phase3 indexed files tooltip and trash workflow"
```

---

### Task 6: Final verification + docs sync

**Files:**
- Modify: `docs/superpowers/plans/2025-03-24-nanobot-agui.md` (勾�?Phase 3)
- Optional: add short notes to AGUI docs if needed

- [x] **Step 1: Run backend web tests**

Run: `pytest tests/web/ -v`  
Expected: PASS

- [x] **Step 2: Run frontend checks**

Run:
```bash
cd frontend
npm run lint
npm run build
```
Expected: PASS

- [x] **Step 3: Manual acceptance script**

Expected:
- skills auto-create + empty state
- skills list A->Z
- click skill previews only `SKILL.md`
- open-folder works for folder/file
- trash single/clear all works with confirmation
- out-of-workspace path rejected

- [x] **Step 3.1: Verify unified error payload contract manually**

Expected:
- `/api/open-folder` 400/404 returns `{error:{code,message,...}}`
- `/api/trash-files` 400 returns `{error:{code,message,...}}`
- `/api/skills` internal error path (if simulated) returns same shape

- [x] **Step 4: Update plan checkboxes and commit**

```bash
git add docs/superpowers/plans/2025-03-24-nanobot-agui.md
git commit -m "chore(plan): mark phase3 sidebar ecosystem complete"
```

---

## Suggested execution checkpoints

- Checkpoint A: 完成 Task 1-3（后�?API + tests）后先验收�?
- Checkpoint B: 完成 Task 4（skills 联动预览）后验收�?
- Checkpoint C: 完成 Task 5-6（索引与回收�?+ 全量验证）后验收�?

