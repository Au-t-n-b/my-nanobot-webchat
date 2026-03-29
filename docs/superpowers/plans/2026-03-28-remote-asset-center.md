# Remote Asset Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不影响现有侧栏其他模块和右侧预览链路的前提下，为 AGUI 接入远端组织资产列表、右侧详情查看，以及与组织中心联通的上传/下载最小闭环。

**Architecture:** 后端新增远端交付中心代理层与会话存储，统一暴露稳定的 `/api/remote-center/*` 与 `/api/remote-assets/*` 契约；前端复用 `Sidebar` 中现有组织资产占位区与 `page.tsx` 右侧面板切换机制，新增远端详情/上传模式而不改动既有技能、产物、会话模块行为。实现顺序优先远端会话 + 组织资产列表/详情 + 下载/复制，再补个人上传能力。

**Tech Stack:** aiohttp, pytest, Next.js 15, React 19, TypeScript

---

### Task 1: 远端代理后端基础设施

**Files:**
- Create: `nanobot/web/remote_center.py`
- Modify: `nanobot/web/routes.py`
- Test: `tests/web/test_api_remote_center.py`

- [ ] **Step 1: Write the failing tests for login/session/project endpoints**

```python
async def test_remote_center_login_returns_session_snapshot(...):
    ...

async def test_remote_center_session_returns_disconnected_by_default(...):
    ...

async def test_remote_center_logout_clears_session(...):
    ...

async def test_remote_center_project_switch_requires_existing_session(...):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_api_remote_center.py -v`
Expected: FAIL with missing routes or missing module errors.

- [ ] **Step 3: Write minimal implementation**

```python
class RemoteCenterSessionStore:
    ...

class RemoteCenterClient:
    ...

async def handle_remote_center_login(...): ...
async def handle_remote_center_session(...): ...
async def handle_remote_center_project(...): ...
async def handle_remote_center_logout(...): ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_api_remote_center.py -v`
Expected: PASS

### Task 2: 组织资产与个人资产后端代理接口

**Files:**
- Modify: `nanobot/web/remote_center.py`
- Modify: `nanobot/web/routes.py`
- Test: `tests/web/test_api_remote_assets.py`

- [ ] **Step 1: Write the failing tests for org assets endpoints**

```python
async def test_get_org_skills_requires_remote_session(...):
    ...

async def test_get_org_skills_returns_mapped_items(...):
    ...

async def test_get_org_skill_detail_returns_can_import_and_can_clone(...):
    ...

async def test_import_org_skill_returns_local_target(...):
    ...

async def test_remote_asset_errors_use_unified_error_shape(...):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_api_remote_assets.py -v`
Expected: FAIL with route not found or response mismatch.

- [ ] **Step 3: Write minimal implementation**

```python
async def handle_remote_org_skills(...): ...
async def handle_remote_org_skill_detail(...): ...
async def handle_remote_org_skill_import(...): ...
async def handle_remote_org_skill_clone(...): ...
async def handle_personal_skills_list(...): ...
async def handle_personal_artifacts_list(...): ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_api_remote_assets.py -v`
Expected: PASS

### Task 3: 个人 Skill / 产物上传后端最小闭环

**Files:**
- Modify: `nanobot/web/remote_center.py`
- Modify: `nanobot/web/routes.py`
- Test: `tests/web/test_api_remote_assets.py`

- [ ] **Step 1: Write the failing tests for personal upload/list endpoints**

```python
async def test_personal_skills_list_returns_mapped_items(...):
    ...

async def test_personal_artifacts_upload_requires_project_or_personal_scope(...):
    ...

async def test_personal_artifacts_upload_from_session_rejects_workspace_escape(...):
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/web/test_api_remote_assets.py -v`
Expected: FAIL with missing handlers or validation mismatch.

- [ ] **Step 3: Write minimal implementation**

```python
async def handle_personal_skills_list(...): ...
async def handle_personal_skills_upload(...): ...
async def handle_personal_artifacts_list(...): ...
async def handle_personal_artifacts_upload(...): ...
async def handle_personal_artifacts_upload_from_session(...): ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/web/test_api_remote_assets.py -v`
Expected: PASS

### Task 4: 远端连接 UI 与右侧面板模式

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/components/SettingsPanel.tsx`
- Modify: `frontend/components/Sidebar.tsx`
- Create: `frontend/components/RemoteAssetDetailPanel.tsx`
- Create: `frontend/components/RemoteAssetUploadPanel.tsx`
- Test: Manual verification in browser

- [ ] **Step 1: Add failing type-level/use-state scaffold**

```tsx
type RightPanelMode = "preview" | "settings" | "config" | "remoteAssetDetail" | "remoteAssetUpload";
```

- [ ] **Step 2: Run lint/type check on touched files**

Run: `npm run lint`
Expected: FAIL until new props/components are wired correctly.

- [ ] **Step 3: Write minimal implementation**

```tsx
const [selectedOrgAssetId, setSelectedOrgAssetId] = useState<string | null>(null);
const openRemoteAssetDetail = useCallback((id: string) => {
  setSelectedOrgAssetId(id);
  setRightPanelMode("remoteAssetDetail");
  setIsPreviewOpen(true);
}, []);

<SettingsPanel onClose={...} onOpenRemoteUpload={...} />
```

- [ ] **Step 4: Re-run lint**

Run: `npm run lint`
Expected: PASS for touched files.

### Task 5: 左侧组织资产列表接入

**Files:**
- Modify: `frontend/components/Sidebar.tsx`
- Test: Manual verification in browser

- [ ] **Step 1: Add failing fetch/render integration**

```tsx
const res = await fetch(apiPath("/api/remote-assets/org-skills", apiBase));
```

- [ ] **Step 2: Run lint to verify incomplete wiring fails or warnings surface**

Run: `npm run lint`
Expected: FAIL or show unresolved state usage before completion.

- [ ] **Step 3: Write minimal implementation**

```tsx
const [orgAssets, setOrgAssets] = useState<OrgAssetItem[]>([]);
...
<button onClick={() => onOpenOrgAssetDetail?.(item.id)}>查看详情</button>
```

- [ ] **Step 4: Re-run lint**

Run: `npm run lint`
Expected: PASS

### Task 6: 右侧详情与上传面板动作联通

**Files:**
- Modify: `frontend/components/RemoteAssetDetailPanel.tsx`
- Modify: `frontend/components/RemoteAssetUploadPanel.tsx`
- Possibly Modify: `frontend/app/page.tsx`
- Test: Manual verification in browser

- [ ] **Step 1: Add failing action flow for import/clone/upload**

```tsx
await fetch(apiPath(`/api/remote-assets/org-skills/${id}/import`, apiBase), ...);
```

- [ ] **Step 2: Run lint**

Run: `npm run lint`
Expected: FAIL until action handlers/state are complete.

- [ ] **Step 3: Write minimal implementation**

```tsx
async function handleImport() { ... }
async function handleCloneToPersonal() { ... }
async function handleSkillUpload() { ... }
async function handleArtifactUpload() { ... }
```

- [ ] **Step 4: Re-run lint and perform targeted manual verification**

Run: `npm run lint`
Expected: PASS

Manual:
- 登录远端中心
- 左侧组织资产可见
- 点击“查看详情”打开右侧详情
- 详情中导入/复制动作可调用后端
- 设置面板中的远端中心区块可登录/登出/切项目
- 独立上传面板可与组织中心接口联通

### Task 7: End-to-end verification

**Files:**
- Modify: `docs/superpowers/specs/2026-03-28-remote-asset-center-design.md` (only if implementation forces contract adjustment)
- Test: `tests/web/test_api_remote_center.py`, `tests/web/test_api_remote_assets.py`, `npm run lint`

- [ ] **Step 1: Run backend tests**

Run: `pytest tests/web/test_api_remote_center.py tests/web/test_api_remote_assets.py -v`
Expected: PASS

- [ ] **Step 2: Run existing nearby backend regression tests**

Run: `pytest tests/web/test_api_skills.py tests/web/test_api_open_folder.py tests/web/test_api_trash.py -v`
Expected: PASS

- [ ] **Step 3: Run frontend lint**

Run: `npm run lint`
Expected: PASS

- [ ] **Step 4: Manual smoke test**

Verify:
- 原有产物区、技能区、会话区不回归
- 组织资产占位位被真实列表替换
- 右侧详情可打开和关闭
- 远端上传/下载链路可用
